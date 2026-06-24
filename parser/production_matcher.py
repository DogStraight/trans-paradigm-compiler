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
        self._log_state(f"处理产生式: {prod}")
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
            self._log_state(f"产生式 {prod} 匹配失败")
            return None
        all_matched_nodes.append(result_node)
    return all_matched_nodes


def try_rule_productions(
    self, context: ParseContext, rule: GrammarRule
) -> Optional[Node]:
    """尝试匹配一个语法规则的全部逻辑"""
    # Pratt 规则
    if getattr(rule, "pratt", False):
        return self._try_pratt_rule(context, rule)

    # 块规则
    block_start = getattr(rule, "block_start", None)
    if block_start is not None and isinstance(block_start, str):
        return self.parse_block(context, start_token=block_start, rule=rule)

    self._log_state(f"尝试匹配规则: {rule.name}")
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes = match_productions(self, context, rule)
    if all_matched_nodes is None:
        return None

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes)

    # 检查结束符
    if not self._check_end_case(context, rule):
        self._restore_current_node(old_node, context)
        return None

    # Inline 扁平化
    inline_result = self._try_inline_rule(
        rule, all_matched_nodes, old_node, context
    )
    if inline_result is not None:
        return inline_result

    self._restore_current_node(old_node, context)
    self._log_state(f"规则 {rule.name} 匹配成功")
    return rule_node
