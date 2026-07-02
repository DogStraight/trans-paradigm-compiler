"""
production_matcher.py — 生产式匹配核心

职责：_process_production_node（dispatch），
_match_productions（循环匹配产生式列表），
_try_rule_productions（单规则匹配全流程）。
"""

from typing import Optional, List
from core.define import Node, GrammarRule
from .parser_context import ParseContext


def process_production_node(self, node: dict, context: ParseContext) -> Optional[Node]:
    """dispatch 到 _parse_* 方法"""
    typ = node.get("type")
    method_name = f"_parse_{typ}"
    method = getattr(self, method_name, None)
    if method is None:
        self._log_state(f"未知节点类型: {typ}")
        return None
    return method(node, context)


def _get_recovery_cfg(self, rule: GrammarRule) -> Optional[dict]:
    """读取规则的 recovery 配置"""
    p = getattr(rule, "parser", {})
    if isinstance(p, dict):
        return p.get("recovery")
    return None


def _get_prod_features(self, rule: GrammarRule, prod: str) -> Optional[dict]:
    """获取产生式特征，带缓存"""
    cache = getattr(rule, "_prod_cache", None)
    if cache is None:
        cache = {}
        setattr(rule, "_prod_cache", cache)
    if prod not in cache:
        from .feature_analyze import analyze_production_features

        cache[prod] = analyze_production_features(prod)
    return cache[prod]


def _try_production(
    self, context: ParseContext, prod: str, rule: GrammarRule, committed: bool
) -> Optional[Node]:
    """尝试匹配单个产生式，失败时如果已提交则产 ErrorNode（吞行）"""
    features = _get_prod_features(self, rule, prod)
    if not features:
        return None
    if not self._prepare_production(context, features):
        return None

    snapshot = context.create_snapshot()
    result = process_production_node(self, features, context)
    if result is not None:
        return result

    # 匹配失败
    context.restore_snapshot(snapshot)

    # 已提交 → 产 ErrorNode（吞行）
    if committed:
        err = Node("Error")
        tokens = []
        # 如果是在匹配具体 token 时失败，也停在该 token 类型上
        stop_types = {"newline"}
        expected_token = None
        if features.get("type") == "token":
            expected_token = features["token_type"]
            stop_types.add(expected_token)
        while context.has_more_tokens():
            t = context.peek_token()
            if t is not None and t.type in stop_types:
                if t.type == expected_token:
                    context.advance_token()  # 消费预期的终止符（如 )），上层不用再管
                break
            if t is not None:
                tokens.append(t)
                context.advance_token()
            else:
                break
        if tokens:
            err.add_attr("raw", " ".join(t.content for t in tokens))
        return err

    return None


def match_productions(
    self, context: ParseContext, rule: GrammarRule
) -> tuple[Optional[List[Node]], Optional[Node]]:
    """匹配规则的所有产生式。

    返回 (matched_nodes, error_node)：
        matched_nodes=None & error_node=None → 全部失败（未提交）
        matched_nodes=[] & error_node=Node   → 提交后部分失败
        matched_nodes=[...] & error_node=None → 完全成功
    """
    recovery = _get_recovery_cfg(self, rule)
    after = None
    committed = False  # 无 recovery → 严格回溯
    if recovery and isinstance(recovery, dict):
        after = recovery.get("after")
        committed = after is not None  # 有 after 显式指定时才提交

    all_matched_nodes = []
    for prod in getattr(rule, "production", []):
        self._log_state(
            f"处理产生式: {prod} | {self._debug_token_info(context)}",
            context=context,
        )

        result_node = _try_production(self, context, prod, rule, committed)
        if result_node is None:
            # 未提交且匹配失败 → 全部失败
            return None, None

        if result_node.node_name == "Error" and committed:
            # 已提交后产出的 ErrorNode → 部分成功
            all_matched_nodes.append(result_node)
            return all_matched_nodes, result_node

        all_matched_nodes.append(result_node)

        # 检查是否到达提交点
        if not committed and after and after in prod:
            committed = True

    return all_matched_nodes, None


def _build_semantic_path(context: ParseContext) -> str:
    """从 path_stack + current_rule 构建当前完整语义路径"""
    rule_name = context.current_rule.name if context.current_rule else "?"
    idx = context.sibling_counter.get(rule_name, 0)
    parts = list(context.path_stack)
    parts.append(f"{rule_name}[{idx}]")
    return "/" + "/".join(parts)


def try_rule_productions(
    self, context: ParseContext, rule: GrammarRule
) -> Optional[Node]:
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
        f"尝试匹配规则: {rule.name} | {self._debug_token_info(context)}",
        context=context,
    )
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes, error_node = match_productions(self, context, rule)
    if all_matched_nodes is None and error_node is None:
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return None

    # 部分成功：有 error_node 时标记规则节点
    if error_node is not None:
        rule_node.add_attr("_error", error_node)

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes or [])

    # 有 error 的规则跳过 end_case 检查（已处于错误状态）
    if error_node is None and not self._check_end_case(context, rule):
        self._restore_current_node(old_node, context)
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return None

    # Inline 扁平化（不扁平包含 error 的规则）
    if error_node is None:
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
