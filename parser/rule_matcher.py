"""
rule_matcher.py — 生产式匹配核心 + 结束符检查

职责：_process_production_node（dispatch），
_match_productions（循环匹配产生式列表），
_try_rule_productions（单规则匹配全流程），
_prepare_production / _check_end_case（结束符检查）。
"""

from core.define import Node, GrammarRule
from .parser_core import ParseContext


def _first_token_of_spec(spec: str, grammar_rules: dict) -> set[str]:
    """计算一个产生式规格字符串的起始 token 类型集合。

    支持:
        "symbol.base.semicolon" → {"symbol.base.semicolon"}
        "@Identifier"          → 查找规则的第一个 token
        "keyword.module"       → {"keyword.module"}
        "@PortParens?"         → 去除 ? 后查找规则
    """
    raw = spec.rstrip("?+*")
    if raw.startswith("@"):
        rule = grammar_rules.get(raw[1:])
        if rule:
            prods = getattr(rule, "production", [])
            if prods:
                return _first_token_of_spec(prods[0], grammar_rules)
        return set()
    return {raw}





def process_production_node(self, node: dict, context: ParseContext) -> Node | None:
    """dispatch 到 _parse_* 方法"""
    typ = node.get("type")
    method_name = f"_parse_{typ}"
    method = getattr(self, method_name, None)
    if method is None:
        self._log_state(f"未知节点类型: {typ}")
        return None
    return method(node, context)


def _get_prod_features(self, rule: GrammarRule, prod: str) -> dict | None:
    """获取产生式特征，带缓存。返回 {"tree": ..., "flat": [...]} 或 None。"""
    cache = getattr(rule, "_prod_cache", None)
    if cache is None:
        cache = {}
        setattr(rule, "_prod_cache", cache)
    if prod not in cache:
        from .rule_selector import (
            analyze_production_features,
            flatten_production_features,
        )

        feat = analyze_production_features(prod)
        if feat is not None:
            cache[prod] = {
                "tree": feat,
                "flat": flatten_production_features(prod),
            }
        else:
            cache[prod] = None
    return cache[prod]


def _try_production(
    self,
    context: ParseContext,
    rule: GrammarRule,
    prod: str,
) -> Node | None:
    """尝试匹配单个产生式。"""
    features = _get_prod_features(self, rule, prod)
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


def try_rule_productions(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """尝试匹配一个语法规则的全部逻辑"""
    # Pratt 规则
    if getattr(rule, "pratt", False):
        return self._try_pratt_rule(context, rule)

    # 作用域推入（如规则有 scope 声明）
    rule_parser = getattr(rule, "parser", {})
    scope_def = rule_parser.get("scope") if isinstance(rule_parser, dict) else None
    scope_pushed = False
    if scope_def and isinstance(scope_def, dict):
        scope_kind = scope_def.get("kind", rule.name)
        scope_name = rule.name
        self.scope_stack.push(scope_name, scope_kind)
        scope_pushed = True

    # 语义路径：规则自然序 +1，入栈（block 规则也走此路径）
    sn = context.sibling_counter.get(rule.name, 0)
    context.sibling_counter[rule.name] = sn + 1
    seg = f"{rule.name}[{sn}]"
    context.path_stack.append(seg)

    # 块规则
    if getattr(rule, "is_block", False):
        result = self.parse_block(context, start_token="", rule=rule)
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return result

    # 记录失败尝试（仅调试收集模式）
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
    inline_result = self._try_inline_rule(
        rule, all_matched_nodes, old_node, context
    )
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


# parser/end_case_checker.py
"""
end_case_checker.py — 生产式准备 & 结束符检查

职责：_prepare_production（匹配前跳空白），
_check_end_case（检查结束符是否匹配）。
"""

from core.define import GrammarRule
from .parser_core import ParseContext
from .rule_selector import analyze_production_features


def prepare_production(self, context: ParseContext, features: dict) -> bool:
    """为匹配产生式做准备：跳过空白/注释。返回 False 表示 token 不足。"""
    should_skip = True

    if features.get("type") == "token" and features.get("token_type") == "comment":
        should_skip = False
    elif features.get("type") == "call":
        ref_rule = self.grammar_rules.get(features["name"])
        if ref_rule and getattr(ref_rule, "is_block", False):
            should_skip = False
    elif features.get("type") in ("optional",):
        should_skip = False
    elif features.get("type") == "repeat" and features.get("min", 0) == 0:
        should_skip = False
    if should_skip:
        self._skip_tokens(context, tuple(self.skip_types))
        # 跳过 production 元素间的注释，同时收集锚点供渲染后回插
        # （模块体注释由 collect_line_comments AST 路径处理，不在此重复）
        while context.has_more_tokens():
            t = context.peek_token()
            if t and t.type == "comment":
                anchor = None
                context.advance_token()
                self._skip_tokens(context, tuple(self.skip_types))
                nxt = context.peek_token()
                if nxt:
                    anchor = nxt.content
                self._line_comment_anchors.append({
                    "text": t.content,
                    "line": t.line,
                    "anchor": anchor,
                })
            else:
                break
        if not context.has_more_tokens():
            return False
    return True


def check_end_case(self, context: ParseContext, rule: GrammarRule) -> bool:
    """检查当前 token 是否匹配规则的终止条件。

    end_case 列表中的 token 支持极性前缀：
        无前缀  — 正匹配：token 在此集合中 → 匹配成功
        ! 前缀  — 反匹配：token 在此集合中 → 匹配失败

    例如: end_case = ["symbol.base.comma", "!symbol.base.dot"]
    """
    if not context.has_more_tokens():
        return True

    token = context.peek_token()
    raw_list = getattr(rule, "end_case", [])

    if token:
        # 分离正/反匹配集合
        pass_tokens: list[str] = []
        fail_tokens: list[str] = []
        for item in raw_list:
            if isinstance(item, str) and item.startswith("!"):
                fail_tokens.append(item[1:])
            else:
                pass_tokens.append(item)

        # 反匹配优先
        if token.type in fail_tokens:
            self._log_state(
                f"✗ end_case(!) 触发: 规则 {rule.name} 遇 '{token.content}' "
                f"(type={token.type})，反匹配 {fail_tokens}",
                context=context,
            )
            return False

        # 正匹配
        if pass_tokens and token.type in pass_tokens:
            return True

    # 没有正匹配项则不检查（非语句级规则）
    if not [t for t in raw_list if not (isinstance(t, str) and t.startswith("!"))]:
        return True

    # 说明 body 由 parse_block 管理，end_case 仅作辅助验证
    for prod in rule.prods:
        try:
            feats = analyze_production_features(prod)
        except Exception:
            continue
        if feats and feats.get("type") == "call":
            inner = self.grammar_rules.get(feats["name"])
            if inner and getattr(inner, "is_block", False):
                return True

    # 增强诊断
    if token:
        self._log_state(
            f"✗ end_case 不匹配: 规则 {rule.name} "
            f"期望 {raw_list}, 实际 '{token.content}' (type={token.type}) "
            f"Ln {token.line}",
            context=context,
        )
    return False
