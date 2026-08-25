"""
_production.py — 生产式解析全流程（合并 rule_matcher + node_parsers）

职责：
    production 元素 dispatch → _parse_token / _parse_call / _parse_seq / etc.
    _try_production → _match_productions → _try_rule_productions（全流程）
    _prepare_production → _check_end_case（辅助检查）
"""

from core.define import Node, GrammarRule, CHILDREN_FIELD
from .parser_core import ParseContext
from ._constants import BLOCK_NODE_NAME, COMMENT_TOKEN_TYPE
from .rule_selector import analyze_production_features, flatten_production_features
from .follow import token_in_follow

import contextlib

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
    self, context: ParseContext, rule: GrammarRule, prods: list | None = None
) -> list[Node | None] | None:
    """匹配规则的所有产生式。返回 matched_nodes 列表，失败返回 None。

    prods 缺省用 rule.prods（普通规则）；块规则块分支传 rule.block_prods
    （内容部分，block_start/block_end 由块路径单独消费）。
    """
    prods = rule.prods if prods is None else prods
    all_matched_nodes: list[Node | None] = []

    for _, prod in enumerate(prods):
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


@contextlib.contextmanager
def rule_frame(self, context: ParseContext, rule: GrammarRule):
    """规则执行帧：作用域 + 语义路径推入，退出自动恢复。

    收敛 try_rule_productions 原先每个 return 分支的手动
    path_stack.pop()/scope_stack.pop()（~8 处重复，易漏一处致栈泄漏）。
    pratt 规则不推帧（原语义：pratt 分支在作用域推入前 return）。
    """
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
    context.path_stack.append(f"{rule.name}[{sn}]")
    try:
        yield
    finally:
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()


def try_block_rule(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """块规则匹配：起止符消费 + 块头内容 + 块体 + FOLLOW 检查。

    有显式 block_start（如 BeginEnd）：自行消费起止符；匿名块（无 block_start）
    由 parse_block 处理、结束符由父规则负责。帧清理（path_stack/scope_stack）
    由调用方 rule_frame 统一处理，本函数只负责节点恢复。
    """
    bs = getattr(rule, "block_start", None)

    if not bs:
        # 匿名块（无 block.start）：由父规则 production 中的 @ 调用触发
        # 块体由 parse_block 处理，结束符由父规则负责消费
        return self.parse_block(context, start_token="", rule=rule)

    # 1) 消费起始符
    self._skip_tokens(context, tuple(self.skip_types))
    tok = context.peek_token()
    if not tok or tok.type != bs:
        self._record_fail_site(
            context,
            rule=rule.name,
            reason=f"block start mismatch: expected {bs}",
        )
        return None
    context.advance_token()

    # 2) 匹配块头内容 production（block_prods，不含 block_start/block_end）
    rule_node = Node(rule.name)
    if tok is not None:
        # 源位置元数据（语义诊断定位用）：块规则锚定起始符
        rule_node._pos_line = tok.line
        rule_node._pos_col = tok.column
    old_node = context.current_node
    context.update_current_node(rule_node)
    all_matched = match_productions(self, context, rule, rule.block_prods)
    if all_matched is None:
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="block header production failed",
        )
        # 恢复 previous current_node（允许 None——fuzz 发现：畸形 ANSI 端口
        # （如 `input [7:0]` 缺端口名）在句子解析上下文里 current_node 可为
        # None，原 assert 直接崩溃。恢复 None 是合法状态，不得用断言兜错误
        # 路径——用户输入必须软失败（截断/解析错误），不能崩。）
        context.update_current_node(old_node)
        return None
    self._bind_attributes(rule_node, rule, all_matched)

    # 3) 解析块体
    block_body = Node(BLOCK_NODE_NAME)
    from .block_parser import parse_block_body

    parse_block_body(self, context, block_body, rule)
    body_children = getattr(block_body, CHILDREN_FIELD, [])
    for child in body_children:
        rule_node.add_sub_node(child)

    # 4) 消费结束符
    be = getattr(rule, "block_end", None) or _get_block_end_for(rule)
    if be:
        self._skip_tokens(context, tuple(self.skip_types))
        tok = context.peek_token()
        if tok and tok.type == be:
            context.advance_token()
            # 结束符后行内注释（`end // comment`）一并消费：
            # 块规则结束符不走 parse_token，注释若残留会停在 token 流，
            # 使外层规则的后继检查（FOLLOW）失败回滚。
            while context.has_more_tokens():
                nxt = context.peek_token()
                if nxt and nxt.type == COMMENT_TOKEN_TYPE:
                    self._comment_anchors.append(
                        {
                            "anchor": tok.content,
                            "text": nxt.content,
                            "line": nxt.line,
                            "type": be,
                        }
                    )
                    context.advance_token()
                else:
                    break

    # 5) FOLLOW 检查（方案 B+）：块规则消费完 block_end 后，下一个 token
    #    也必须是派生 FOLLOW 中的合法后继——与普通规则统一（不再跳过）。
    #    块规则自身 production 完整（首尾字面 token），check_end_case 的
    #    "引用块规则"guard 不触发，走派生 FOLLOW 硬检查。
    if not self._check_end_case(context, rule):
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="block FOLLOW mismatch",
        )
        self._restore_current_node(old_node, context)
        return None

    self._restore_current_node(old_node, context)
    return rule_node


def try_plain_rule(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """普通规则匹配链：production 匹配 → 属性绑定 → FOLLOW 检查 → inline。

    帧清理（path_stack/scope_stack）由调用方 rule_frame 统一处理，本函数
    只负责节点恢复。
    """
    self._log_state(
        lambda: f"尝试规则: {rule.name} | {self._debug_token_info(context)}",
        context=context,
    )
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    _start_tok = context.peek_token()
    if _start_tok is not None:
        # 源位置元数据（语义诊断定位用）：普通规则锚定 production 首个 token
        rule_node._pos_line = _start_tok.line
        rule_node._pos_col = _start_tok.column
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes = match_productions(self, context, rule)
    if all_matched_nodes is None:
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="production match failed",
        )
        return None

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes)

    # 后继检查（派生 FOLLOW 硬检查）
    if not self._check_end_case(context, rule):
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="FOLLOW mismatch",
        )
        self._restore_current_node(old_node, context)
        return None

    # Inline 扁平化
    inline_result = self._try_inline_rule(rule, all_matched_nodes, old_node, context)
    if inline_result is not None:
        return inline_result

    self._restore_current_node(old_node, context)
    self._log_state(f"✓ 规则 {rule.name} 匹配成功", context=context)
    return rule_node


def try_rule_productions(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """尝试匹配一个语法规则的全部逻辑（薄调度器）。

    三形态分派：pratt / 块（_try_block_rule）/ 普通（_try_plain_rule）。
    帧管理（作用域 + 语义路径）由 rule_frame 统一收敛——原单函数 ~180 行、
    8 处重复栈清理（path_stack.pop/scope_stack.pop）易漏，拆后各职责独立。
    """
    # 停点/trace：按规则名或 token 位置过滤（仅真实 Parser 有此方法）
    trace_fn = getattr(self, "_maybe_trace", None)
    if trace_fn is not None:
        trace_fn(context, rule.name)

    # Pratt 规则（不推帧，原语义：pratt 分支在作用域推入前 return）
    if getattr(rule, "pratt", False):
        return self._try_pratt_rule(context, rule)

    with self._rule_frame(context, rule):
        if getattr(rule, "is_block", False):
            return self._try_block_rule(context, rule)
        return self._try_plain_rule(context, rule)


# ── 生产式准备 & 结束符检查 ──


def prepare_production(self, context: ParseContext, features: dict) -> bool:
    """为匹配产生式做准备：跳过空白/注释。"""
    ftype = features["type"] if "type" in features else None
    should_skip = True

    if ftype == "token":
        if features.get("token_type") == COMMENT_TOKEN_TYPE:
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
            if t and t.type == COMMENT_TOKEN_TYPE:
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
    """检查规则匹配后当前 token 是否为合法后继（派生 FOLLOW 硬性检查）。

    判定顺序：
      1. 跳过 trivia（newline/space.fold/comment）后取检查 token——FOLLOW
         是 token 级后继集，trivia 不是语法后继
      2. 块 body 辅助验证（production 引用块规则、body 由 parse_block 管理
         的规则）→ 接受——块边界由结构决定，FOLLOW 检查不适用
      3. 派生 FOLLOW 硬性检查（token ∉ FOLLOW → 拒绝）——parser/follow.py
         从 production 结构机械推导，语法是唯一真相源
      4. 无派生 FOLLOW（不可达规则，到不了此检查）→ 接受
    """
    if not context.has_more_tokens():
        return True

    # 1. peek 跳过 trivia（不消费 token，检查后指针不动）
    token = None
    offset = 0
    while True:
        tok = context.peek_token(offset)
        if tok is None:
            return True
        if tok.type in self.skip_types or tok.type == COMMENT_TOKEN_TYPE:
            offset += 1
            continue
        token = tok
        break

    # 2. 若 body 由 parse_block 管理，边界由结构决定，FOLLOW 检查不适用。
    #    复用 _get_prod_features 缓存（key = rule.name::prod）——原直接
    #    analyze_production_features 每次运行期重新解析 production 字符串
    #    （picorv32 单管线 11.7 万次 build_tree，最大热点）。
    for prod in rule.prods:
        feats = _get_prod_features(rule, prod)
        tree = feats["tree"] if feats else None
        if tree and tree.get("type") == "call":
            inner = self.grammar_rules.get(tree["name"])
            if inner and getattr(inner, "is_block", False):
                return True

    # 3. 派生 FOLLOW 硬性检查
    follows = getattr(self, "_follows", None)
    follow = follows.get(rule.name) if follows is not None else None
    if follow:
        if token_in_follow(token.type, follow):
            return True
        self._log_state(
            f"✗ 后继检查(FOLLOW): 规则 {rule.name} "
            f"后继 '{token.content}' (type={token.type}) "
            f"Ln {token.line} 不在派生 FOLLOW 中",
            context=context,
        )
        return False

    # 4. 无派生 FOLLOW（不可达规则）→ 接受
    return True


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
        if nxt and nxt.type == COMMENT_TOKEN_TYPE:
            self._comment_anchors.append(
                {
                    "anchor": current_token.content,
                    "text": nxt.content,
                    "line": nxt.line,
                    "type": token_type,
                }
            )
            # 注释 attachment（ADR-0006 阶段 4 注释遍）：同步挂到当前节点，
            # renderer 用 line_suffix 渲染为 Doc 一等公民。下划线属性穿过
            # normalizer（transform/normalizer.py 保留）、Node.dump 过滤。
            cur_node = getattr(context, "current_node", None)
            if isinstance(cur_node, Node):
                attached = getattr(cur_node, "_attached_comments", None)
                if attached is None:
                    attached = []
                    cur_node.add_attr("_attached_comments", attached)
                attached.append(nxt.content)
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
    # 入口跳过 trivia（newline/space.fold）：seq 是嵌套元素（repeat 迭代项、
    # 括号组等），其子 token 遇换行（多行敏感列表 `a or b\n or c`）需能继续；
    # 规则级跳过由 _try_production 的 prepare_production 负责，嵌套 seq 在此补齐。
    if hasattr(self, "_skip_tokens"):
        self._skip_tokens(context, tuple(self.skip_types))
    with context:
        seq_node = Node("seq")
        for _, item in enumerate(items):
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
    # 入口跳过 trivia：choice 内分支 token 从非 trivia 位置尝试，避免行首
    # newline 使所有分支（纯 token 分支）失配（多行表达式/列表的续行元素）。
    if hasattr(self, "_skip_tokens"):
        self._skip_tokens(context, tuple(self.skip_types))
    for _, alt in enumerate(alternatives):
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
    setattr(r, CHILDREN_FIELD, nodes[:])
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
    """从规则提取块结束符（block_end 由 production 首尾字面 token 推导）。"""
    if hasattr(rule, "block_end") and rule.block_end:
        return rule.block_end
    return ""


# 公开别名（保持与 parser_core 中 _repeat_loop = repeat_loop 的兼容）
repeat_loop = _repeat_loop
