"""
atom_parser.py — 原子规则 & Pratt 桥接

职责：_parse_atom（按序尝试原子规则），
_try_pratt_rule（调用 Pratt 解析器处理表达式）。
"""

from typing import Optional
from core.define import Node, GrammarRule
from .parser_context import ParseContext
import parser.pratt_parser as pratt_parser


def parse_atom(self, context: ParseContext) -> tuple[Optional[Node], int]:
    """尝试按顺序匹配原子规则，返回 (node, consumed) 或 (None, 0)。"""
    start_ptr = context.token_pointer
    for rule in self.atomic_rules:
        snapshot = context.create_snapshot()
        node = self._try_rule_productions(context, rule)
        if node is not None:
            consumed = context.token_pointer - start_ptr
            return node, consumed
        context.restore_snapshot(snapshot)
    return None, 0


def try_pratt_rule(
    self, context: ParseContext, rule: GrammarRule
) -> Optional[Node]:
    """使用 Pratt 解析器解析表达式规则"""
    self._log_state(f"使用 Pratt 解析器解析规则: {rule.name}")
    if not context.has_more_tokens():
        self._log_state("Pratt 解析: 没有可用 token")
        return None

    start = context.token_pointer
    stop_tokens = (
        set(getattr(rule, "end_case", []))
        if getattr(rule, "end_case", None)
        else None
    )

    def atom_parser(tokens_list, idx):
        old_ptr = context.token_pointer
        context.token_pointer = idx
        node, consumed = parse_atom(self, context)
        context.token_pointer = old_ptr
        return node, consumed

    try:
        ast_node, consumed = pratt_parser.parse_with_count(
            context.tokens,
            start,
            self.operator_defs,
            atom_parser=atom_parser,
            stop_tokens=stop_tokens,
        )
    except ValueError as e:
        self._log_state(f"Pratt 解析: 不适合作为表达式 - {e}")
        return None
    except Exception as e:
        self._log_state(f"Pratt 解析失败: {e}")
        self._warn(f"Pratt 表达式解析失败: {e}")
        return None

    if ast_node is None or consumed == 0:
        self._log_state("Pratt 解析: 未消费任何 token")
        return None

    context.token_pointer = start + consumed
    self._log_state(f"Pratt 解析成功，消耗 {consumed} 个 token")
    return ast_node
