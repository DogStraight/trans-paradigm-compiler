"""
_production.py — 生产式解析全流程（合并 rule_matcher + node_parsers）

职责：
    production 元素 dispatch → _parse_token / _parse_call / _parse_seq / etc.
    _try_production → _match_productions → _try_rule_productions（全流程）
    _prepare_production → _check_end_case（辅助检查）
"""

from core.define import Node, GrammarRule
from .parser_core import ParseContext
from .rule_selector import analyze_production_features, flatten_production_features

# ── production 元素 dispatch 表 ──
# 取代 getattr(self, f"_parse_{typ}") 的动态查找
_DISPATCH: dict[str, str] = {
    "token": "_parse_token",
    "call": "_parse_call",
    "seq": "_parse_seq",
    "choice": "_parse_choice",
    "repeat": "_parse_repeat",
    "optional": "_parse_optional",
    "plus": "_parse_plus",
}


def process_production_node(self, node: dict, context: ParseContext) -> Node | None:
    """dispatch 到 _parse_* 方法（查表而非 getattr）"""
    # 用 [] 直接索引代替 .get() 避免两次 dict 查找
    typ = node["type"] if "type" in node else None
    if typ is None:
        return None
    method_name = _DISPATCH.get(typ)
    if method_name is None:
        return None
    method = getattr(self, method_name, None)
    if method is None:
        return None
    return method(node, context)


# ── 生产式特征缓存 ──

_prod_feat_cache: dict[str, dict | None] = {}


def _get_prod_features(rule: GrammarRule, prod: str) -> dict | None:
    """获取产生式特征（带缓存）。"""
    key = f"{rule.name}::{prod}"
    cached = _prod_feat_cache.get(key)
    if cached is not None:
        return cached
    feat = analyze_production_features(prod)
    if feat is not None:
        result = {
            "tree": feat,
            "flat": flatten_production_features(prod),
        }
    else:
        result = None
    _prod_feat_cache[key] = result
    return result


# ── 产生式匹配 ──


def _try_production(
    self,
    context: ParseContext,
    rule: GrammarRule,
    prod: str,
) -> Node | None:
    """尝试匹配单个产生式。"""
    features = _get_prod_features(rule, prod)
    if not features:
        return None
    feature_tree = features["tree"]
    if not self._prepare_production(context, feature_tree):
        return None

    snapshot = context.create_snapshot()
    result = process_production_node(self, feature_tree, context)
    if result is not None:
        return result

    context.restore_snapshot(snapshot)
    return None


def match_productions(
    self, context: ParseContext, rule: GrammarRule
) -> list[Node | None] | None:
    """匹配规则的所有产生式。返回 matched_nodes 列表，失败返回 None。"""
    prods = rule.prods
    all_matched_nodes: list[Node | None] = []

    for i, prod in enumerate(prods):
        self._log_state(lambda: f"产生式: {prod} | {self._debug_token_info(context)}")

        result_node = _try_production(self, context, rule, prod)
        if result_node is None:
            return None

        all_matched_nodes.append(result_node)

    return all_matched_nodes


def _first_token_of_spec(spec: str, grammar_rules: dict) -> set[str]:
    """计算一个产生式规格字符串的起始 token 类型集合。"""
    raw = spec.rstrip("?+*")
    if raw.startswith("@"):
        rule = grammar_rules.get(raw[1:])
        if rule:
            prods = getattr(rule, "production", [])
            if prods:
                return _first_token_of_spec(prods[0], grammar_rules)
        return set()
    return {raw}


# ── 规则匹配全流程 ──


def try_rule_productions(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """尝试匹配一个语法规则的全部逻辑"""
    # Pratt 规则
    if getattr(rule, "pratt", False):
        return self._try_pratt_rule(context, rule)

    # 作用域推入
    rule_parser = getattr(rule, "parser", {})
    scope_def = rule_parser.get("scope") if isinstance(rule_parser, dict) else None
    scope_pushed = False
    if scope_def and isinstance(scope_def, dict):
        scope_kind = scope_def.get("kind", rule.name)
        self.scope_stack.push(rule.name, scope_kind)
        scope_pushed = True

    # 语义路径
    sn = context.sibling_counter.get(rule.name, 0)
    context.sibling_counter[rule.name] = sn + 1
    seg = f"{rule.name}[{sn}]"
    context.path_stack.append(seg)

    # 块规则
    if getattr(rule, "is_block", False):
        bs = getattr(rule, "block_start", None)

        if bs:
            # 有显式 block.start 的块规则（如 BeginEnd）：自行消费起止符
            # 1) 消费起始符
            self._skip_tokens(context, tuple(self.skip_types))
            tok = context.peek_token()
            if not tok or tok.type != bs:
                context.path_stack.pop()
                if scope_pushed:
                    self.scope_stack.pop()
                return None
            context.advance_token()

            # 2) 正常匹配 production（如 @BlockLabel?）
            rule_node = Node(rule.name)
            old_node = context.current_node
            context.update_current_node(rule_node)
            all_matched = match_productions(self, context, rule)
            if all_matched is None:
                assert old_node is not None
                context.update_current_node(old_node)
                context.path_stack.pop()
                if scope_pushed:
                    self.scope_stack.pop()
                return None
            self._bind_attributes(rule_node, rule, all_matched)

            # 3) 解析块体
            block_body = Node("Block")
            from .block_parser import parse_block_body

            parse_block_body(self, context, block_body, rule)
            body_children = getattr(block_body, "sub_node", [])
            for child in body_children:
                rule_node.add_sub_node(child)

            # 4) 消费结束符
            be = getattr(rule, "block_end", None) or _get_block_end_for(rule)
            if be:
                self._skip_tokens(context, tuple(self.skip_types))
                tok = context.peek_token()
                if tok and tok.type == be:
                    context.advance_token()

            self._restore_current_node(old_node, context)
            context.path_stack.pop()
            if scope_pushed:
                self.scope_stack.pop()
            return rule_node
        else:
            # 匿名块（无 block.start）：由父规则 production 中的 @ 调用触发
            # 块体由 parse_block 处理，结束符由父规则负责消费
            result = self.parse_block(context, start_token="", rule=rule)
            context.path_stack.pop()
            if scope_pushed:
                self.scope_stack.pop()
            return result

    # 记录失败尝试
    current_token = context.peek_token()
    if getattr(self, "_collect_failures", False):
        self._failure_attempts.append(
            {
                "rule": rule.name,
                "token": str(current_token.content) if current_token else "EOF",
                "token_index": context.token_pointer,
                "token_type": current_token.type if current_token else "EOF",
                "path": "/".join(context.path_stack),
            }
        )

    self._log_state(
        lambda: f"尝试规则: {rule.name} | {self._debug_token_info(context)}",
        context=context,
    )
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes = match_productions(self, context, rule)
    if all_matched_nodes is None:
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return None

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes)

    # end_case 检查
    if not self._check_end_case(context, rule):
        self._restore_current_node(old_node, context)
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return None

    # Inline 扁平化
    inline_result = self._try_inline_rule(rule, all_matched_nodes, old_node, context)
    if inline_result is not None:
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return inline_result

    self._restore_current_node(old_node, context)
    self._log_state(f"✓ 规则 {rule.name} 匹配成功", context=context)
    context.path_stack.pop()
    if scope_pushed:
        self.scope_stack.pop()
    return rule_node


# ── 生产式准备 & 结束符检查 ──


def prepare_production(self, context: ParseContext, features: dict) -> bool:
    """为匹配产生式做准备：跳过空白/注释。"""
    ftype = features["type"] if "type" in features else None
    should_skip = True

    if ftype == "token":
        if features.get("token_type") == "comment":
            should_skip = False
    elif ftype == "call":
        ref_rule = self.grammar_rules.get(features["name"])
        if ref_rule and getattr(ref_rule, "is_block", False):
            should_skip = False
    elif ftype == "optional":
        should_skip = False
    elif ftype == "repeat" and features.get("min", 0) == 0:
        should_skip = False
    if should_skip:
        self._skip_tokens(context, tuple(self.skip_types))
        while context.has_more_tokens():
            t = context.peek_token()
            if t and t.type == "comment":
                context.advance_token()
                self._skip_tokens(context, tuple(self.skip_types))
                nxt = context.peek_token()
                self._line_comment_anchors.append(
                    {
                        "text": t.content,
                        "line": t.line,
                        "anchor": nxt.content if nxt else None,
                    }
                )
            else:
                break
        if not context.has_more_tokens():
            return False
    return True


def check_end_case(self, context: ParseContext, rule: GrammarRule) -> bool:
    """检查当前 token 是否匹配规则的终止条件。"""
    if not context.has_more_tokens():
        return True

    token = context.peek_token()
    raw_list = getattr(rule, "end_case", [])

    if token:
        pass_tokens: list[str] = []
        fail_tokens: list[str] = []
        for item in raw_list:
            if isinstance(item, str) and item.startswith("!"):
                fail_tokens.append(item[1:])
            else:
                pass_tokens.append(item)

        if token.type in fail_tokens:
            self._log_state(
                f"✗ end_case(!) 触发: 规则 {rule.name} 遇 '{token.content}' "
                f"(type={token.type})，反匹配 {fail_tokens}",
                context=context,
            )
            return False

        if pass_tokens and token.type in pass_tokens:
            return True

    # 无正匹配项则跳过检查
    if not [t for t in raw_list if not (isinstance(t, str) and t.startswith("!"))]:
        return True

    # 若 body 由 parse_block 管理，end_case 仅作辅助验证
    for prod in rule.prods:
        feats = analyze_production_features(prod)
        if feats and feats.get("type") == "call":
            inner = self.grammar_rules.get(feats["name"])
            if inner and getattr(inner, "is_block", False):
                return True

    # 定长 production（顶层无 ? * + 后缀）：production 已精确消费规则应占的 token，
    # 当前 token 是父规则的责任。正匹配项此时仅作日志警告，不拒绝规则。
    # 这使 end_case 的 "symbol.base.comma" / "bracket.r_parentheses" 等
    # 可推导项可以从语法规则中安全移除，只在变长 production 中保留硬要求。
    if not _has_variable_production(rule):
        if token:
            self._log_state(
                f"~ end_case 不匹配(定长production,仅警告): 规则 {rule.name} "
                f"期望 {raw_list}, 实际 '{token.content}' (type={token.type}) "
                f"Ln {token.line}",
                context=context,
            )
        return True

    if token:
        self._log_state(
            f"✗ end_case 不匹配: 规则 {rule.name} "
            f"期望 {raw_list}, 实际 '{token.content}' (type={token.type}) "
            f"Ln {token.line}",
            context=context,
        )
    return False


def _has_variable_production(rule: GrammarRule) -> bool:
    """检查规则的 production 列表是否含有变长元素（顶层 ? * + 后缀）。

    定长 production 的所有元素都是固定匹配（无 ? * +），解析器已精确消费
    规则应有的 token，end_case 正匹配仅为建议。变长 production 需要
    end_case 来确定何时停止重复匹配。
    """
    for prod in getattr(rule, "production", []):
        if not isinstance(prod, str):
            continue
        # 扫描顶层字符（不在括号内）是否有 ? * + 后缀
        depth = 0
        for ch in prod:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif depth == 0 and ch in ('?', '*', '+'):
                return True
    return False


# ── 原子解析器：_parse_token / _parse_call / _parse_seq / etc. ──


def parse_token(self, node: dict, context: ParseContext) -> Node | None:
    """匹配一个普通 token"""
    token_type: str = node["token_type"]
    self._log_state(f"解析token: {token_type}")

    if not context.has_more_tokens():
        self._log_state("无更多token可解析")
        return None

    current_token = context.peek_token(offset=0)
    if current_token is None:
        return None

    if token_type != current_token.type:
        self._log_state(
            lambda: f"token类型不匹配: 期望 {token_type}, 实际 {current_token.type} | {self._debug_token_info(context)}"
        )
        return None

    parsed_node = Node(token_type)
    parsed_node.add_attr("value", current_token.content)
    context.advance_token()

    # 收集紧随当前 token 的 inline comment
    while True:
        nxt = context.peek_token(offset=0)
        if nxt and nxt.type == "comment":
            self._comment_anchors.append(
                {
                    "anchor": current_token.content,
                    "text": nxt.content,
                    "line": nxt.line,
                    "type": token_type,
                }
            )
            context.advance_token()
        else:
            break

    self._log_state(
        lambda: f"token {token_type} ok | {self._debug_token_info(context)}"
    )
    return parsed_node


def parse_call(self, node: dict, context: ParseContext) -> Node | None:
    """调用另一个语法规则。"""
    rule_name = node["name"]
    self._log_state(
        lambda: f"调用规则: {rule_name} | {self._debug_token_info(context)}"
    )
    snapshot = context.create_snapshot()

    target_rule = self.grammar_rules.get(rule_name)
    if target_rule is None:
        context.restore_snapshot(snapshot)
        return None

    result_node = self._try_rule_productions(context, target_rule)
    if result_node is None:
        context.restore_snapshot(snapshot)
        return None

    return result_node


def parse_seq(self, node: dict, context: ParseContext) -> Node | None:
    """顺序序列：所有子项依次匹配"""
    items = node["items"]
    self._log_state(lambda: f"解析序列节点 | {self._debug_token_info(context)}")
    with context:
        seq_node = Node("seq")
        for idx, item in enumerate(items):
            result = self._process_production_node(item, context)
            if result is None:
                return None
            seq_node.add_sub_node(result)
        self._log_state(lambda: f"序列解析成功 | {self._debug_token_info(context)}")
        return seq_node


def parse_choice(self, node: dict, context: ParseContext) -> Node | None:
    """分支选择：依次尝试每个分支"""
    alternatives = node["alternatives"]
    self._log_state(lambda: f"解析分支节点 | {self._debug_token_info(context)}")
    original_pointer = context.token_pointer
    for idx, alt in enumerate(alternatives):
        context.token_pointer = original_pointer
        with context:
            result = self._process_production_node(alt, context)
            if result is not None:
                return result
    context.token_pointer = original_pointer
    self._log_state(lambda: f"所有分支匹配失败 | {self._debug_token_info(context)}")
    return None


def _repeat_loop(
    self,
    elem: dict,
    context: ParseContext,
    min_count: int = 0,
    max_count: int | None = None,
) -> list[Node | None] | None:
    """循环匹配 elem，返回压平后的节点列表。"""
    nodes = []
    while True:
        snapshot = context.create_snapshot()
        result = self._process_production_node(elem, context)
        if result is None:
            context.restore_snapshot(snapshot)
            break
        nodes.append(result)
        if max_count is not None and len(nodes) >= max_count:
            break
    return nodes if len(nodes) >= min_count else None


def parse_repeat(self, node: dict, context: ParseContext) -> Node | None:
    """零次或多次重复"""
    elem = node["elem"]
    self._log_state(lambda: f"解析重复节点 | {self._debug_token_info(context)}")
    nodes = _repeat_loop(self, elem, context) or []
    self._log_state(
        lambda: f"重复完成, cnt={len(nodes)} | {self._debug_token_info(context)}"
    )
    r = Node("repeat", items=nodes)
    r.sub_node = nodes[:]
    return r


def parse_optional(self, node: dict, context: ParseContext) -> Node | None:
    """可选（零次或一次）"""
    elem = node["elem"]
    self._log_state(lambda: f"解析可选节点 | {self._debug_token_info(context)}")
    nodes = _repeat_loop(self, elem, context, min_count=0, max_count=1)
    optional_node = Node("optional")
    if nodes and nodes[0] is not None:
        optional_node.add_sub_node(nodes[0])
    return optional_node


def parse_plus(self, node: dict, context: ParseContext) -> Node | None:
    """至少一次重复"""
    elem = node["elem"]
    self._log_state(lambda: f"解析至少一次重复节点 | {self._debug_token_info(context)}")
    nodes = _repeat_loop(self, elem, context, min_count=1)
    if nodes is None:
        return None
    plus_node = Node("plus", items=nodes)
    for child in nodes:
        plus_node.add_sub_node(child) if child is not None else None
    return plus_node


def _get_block_end_for(rule) -> str:
    """从规则中提取块结束符 token 类型。"""
    if hasattr(rule, "block_end") and rule.block_end:
        return rule.block_end
    for item in getattr(rule, "end_case", []):
        if isinstance(item, str) and not item.startswith("!"):
            return item
    return ""


# 公开别名（保持与 parser_core 中 _repeat_loop = repeat_loop 的兼容）
repeat_loop = _repeat_loop
