"""
production_matcher.py — 生产式匹配核心

职责：_process_production_node（dispatch），
_match_productions（循环匹配产生式列表），
_try_rule_productions（单规则匹配全流程）。
"""

from typing import Optional, List
from core.define import Node, GrammarRule
from .parser_context import ParseContext


def process_production_node(
    self, node: dict, context: ParseContext
) -> Optional[Node]:
    """dispatch 到 _parse_* 方法"""
    typ = node.get("type")
    method_name = f"_parse_{typ}"
    method = getattr(self, method_name, None)
    if method is None:
        self._log_state(f"未知节点类型: {typ}")
        return None
    return method(node, context)


def match_productions(
    self, context: ParseContext, rule: GrammarRule
) -> Optional[List[Node]]:
    """匹配规则的所有产生式。成功返回节点列表，任一产生式失败返回 None。"""
    all_matched_nodes = []
    for prod in getattr(rule, "production", []):
        self._log_state(
            f"处理产生式: {prod} | {self._debug_token_info(context)}",
            context=context,
        )
        from .feature_analyze import analyze_production_features
        features = analyze_production_features(prod)
        if not features:
            continue

        if not self._prepare_production(context, features):
            break

        snapshot = context.create_snapshot()
        result_node = process_production_node(self, features, context)
        if result_node is None:
            context.restore_snapshot(snapshot)
            self._log_state(
                f"✗ 产生式 {prod} 匹配失败 | {self._debug_token_info(context)}",
                context=context,
            )
            return None
        all_matched_nodes.append(result_node)
    return all_matched_nodes


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

    # 语义路径：规则自然序 +1，入栈（block 规则也走此路径）
    sn = context.sibling_counter.get(rule.name, 0)
    context.sibling_counter[rule.name] = sn + 1
    seg = f"{rule.name}[{sn}]"
    context.path_stack.append(seg)

    # 块规则
    if getattr(rule, "is_block", False):
        result = self.parse_block(context, start_token="", rule=rule)
        context.path_stack.pop()
        return result

    # 记录失败尝试（成功后清空）
    current_token = context.peek_token()
    if hasattr(self, "_failure_attempts"):
        self._failure_attempts.append({
            "rule": rule.name,
            "token": str(current_token.content) if current_token else "EOF",
            "token_index": context.token_pointer,
            "token_type": current_token.type if current_token else "EOF",
            "path": "/".join(context.path_stack),
        })

    self._log_state(
        f"尝试匹配规则: {rule.name} | {self._debug_token_info(context)}",
        context=context,
    )
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes = match_productions(self, context, rule)
    if all_matched_nodes is None:
        context.path_stack.pop()
        return None

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes)

    # 检查结束符/终止符（含 end_case 正匹配 + forbidden_next 反匹配）
    if not self._check_end_case(context, rule):
        self._restore_current_node(old_node, context)
        context.path_stack.pop()
        return None

    # Inline 扁平化
    inline_result = self._try_inline_rule(
        rule, all_matched_nodes, old_node, context
    )
    if inline_result is not None:
        context.path_stack.pop()
        return inline_result

    self._restore_current_node(old_node, context)
    self._log_state(
        f"✓ 规则 {rule.name} 匹配成功", context=context
    )
    context.path_stack.pop()
    return rule_node
