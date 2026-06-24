"""
block_parser.py — 块 & 语句级解析

职责：parse_sentence, _resolve_block_rule, _consume_start_token,
_parse_block_body, parse_block。
"""

from typing import Optional, List, Tuple
from core.define import Node, GrammarRule
from .parser_context import ParseContext


def parse_sentence(self, context: ParseContext) -> Optional[Node]:
    """解析一条语句：根据当前 token 选择候选规则并尝试匹配。"""
    if not context.has_more_tokens():
        return None

    current = context.peek_token()
    if current is None:
        return None

    candidates = self.rule_selector.get_candidate_rules(current)
    if not candidates:
        return None

    for rule in candidates:
        snapshot = context.create_snapshot()
        node = self._try_rule_productions(context, rule)
        if node is not None:
            return node
        context.restore_snapshot(snapshot)

    self._warn(
        f"所有候选规则匹配失败: '{current.content}' (type: {current.type})"
    )
    return None


def resolve_block_rule(
    self, start_token: Optional[str]
) -> Optional[Tuple[GrammarRule, str, Optional[str]]]:
    """查找起始符对应的块规则，返回 (matched_rule, block_name, end_token) 或 None"""
    block_rule_name = (
        self.rule_selector.get_block_rule(start_token)
        if start_token is not None
        else None
    )
    self._log_state(f"找到块规则: {block_rule_name}")
    matched_rule = (
        self.grammar_rules.get(block_rule_name) if block_rule_name else None
    )
    if matched_rule is None:
        self._log_state(f"未找到匹配的块规则: {start_token}")
        return None
    block_name = matched_rule.name
    end_token = getattr(matched_rule, "block_end", None)
    return matched_rule, block_name, end_token


def consume_start_token(self, context: ParseContext, start_token: str) -> bool:
    """跳过空白并消费起始符，成功返回 True"""
    self._skip_tokens(context, tuple(self.skip_types))
    current = context.peek_token()
    if not current:
        self._log_state(f"期望块开始标记 {start_token}，文件已结束")
        return False
    if current.type == start_token:
        context.advance_token()
        return True
    self._log_state(f"期望块开始标记 {start_token}，实际为 {current.type}")
    return False


def parse_block_body(
    self, context: ParseContext, block_node: Node, end_token: Optional[str]
) -> None:
    """循环解析句子直到遇到结束符或文件末尾，将子句添加到 block_node"""
    while context.has_more_tokens():
        self._skip_tokens(context, tuple(self.skip_types))
        if not context.has_more_tokens():
            break

        if not context.has_more_tokens():
            break
        current = context.peek_token()
        assert current is not None
        if current.type == end_token:
            if context.end_verify:
                snapshot = context.create_snapshot()
                context.advance_token()
                self._skip_tokens(context, tuple(self.skip_types))
                if context.has_more_tokens():
                    next_tok = context.peek_token()
                    if (
                        getattr(next_tok, "type", None)
                        in self.rule_selector.start_token_map
                    ):
                        context.restore_snapshot(snapshot)
                        context.advance_token()
                        continue
                context.restore_snapshot(snapshot)
                context.advance_token()
                break
            context.advance_token()
            break
        stmt_node = parse_sentence(self, context)
        if stmt_node is None:
            break
        block_node.add_sub_node(stmt_node)


def parse_block(
    self,
    context: ParseContext,
    start_token: Optional[str] = None,
    rule: Optional[GrammarRule] = None,
) -> Optional[Node]:
    """解析一个代码块。"""
    if rule is not None:
        matched_rule = rule
        block_name = rule.name
        end_token = getattr(rule, "block_end", None)
    else:
        resolved = resolve_block_rule(self, start_token)
        if resolved is None:
            return None
        matched_rule, block_name, end_token = resolved

    self._log_state(
        f"进入 parse_block, block={block_name}, start_token={start_token}, "
        f"当前 token: {context.peek_token() if context.has_more_tokens() else 'EOF'}"
    )

    if start_token and not consume_start_token(self, context, start_token):
        return None

    block_node = Node(block_name)
    old_verify = context.end_verify
    context.end_verify = getattr(matched_rule, "end_verify", False)
    parse_block_body(self, context, block_node, end_token)
    context.end_verify = old_verify
    return block_node
