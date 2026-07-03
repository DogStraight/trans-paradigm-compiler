"""
block_parser.py — 块 & 语句级解析

职责：parse_sentence, _resolve_block_rule, _consume_start_token,
_parse_block_body, parse_block。
"""

from core.define import Node, GrammarRule
from .parser_core import ParseContext


def parse_sentence(self, context: ParseContext) -> Node | None:
    """解析一条语句：根据当前 token 选择候选规则并尝试匹配。"""
    if not context.has_more_tokens():
        return None

    current = context.peek_token()
    if current is None:
        return None

    candidates = self.rule_selector.get_candidate_rules(
        current,
        self.pre_symbols,
        self.pre_hints,
        self.scope_stack.lookup,
    )
    self._log_state(
        f"parse_sentence: {self._debug_token_info(context)} "
        f"candidates={[r.name for r in candidates]}",
        context=context,
    )
    if not candidates:
        return None

    for rule in candidates:
        snapshot = context.create_snapshot()
        scope_depth = self.scope_stack.snapshot()
        node = self._try_rule_productions(context, rule)
        if node is not None:
            return node
        self.scope_stack.restore(scope_depth)
        context.restore_snapshot(snapshot)

    # 所有候选规则都匹配失败 → 简略警告
    rule_hint = ", ".join(r.name for r in candidates[:5])
    if len(candidates) > 5:
        rule_hint += f" ... ({len(candidates)} 个候选)"
    self._warn(
        f"匹配失败: '{current.content}' Ln {current.line} " f"→ 尝试过: {rule_hint}",
        context=context,
    )
    return None


def _get_block_end(rule: GrammarRule) -> str:
    """从规则的 end_case 中提取块结束符（第一个正匹配项，无则返回空字符串）"""
    for item in getattr(rule, "end_case", []):
        if isinstance(item, str) and not item.startswith("!"):
            return item
    return ""


def resolve_block_rule(
    self, start_token: str | None
) -> tuple[GrammarRule, str, str | None] | None:
    """查找起始符对应的块规则，返回 (matched_rule, block_name, end_token) 或 None"""
    block_rule_name = (
        self.rule_selector.get_block_rule() if start_token is not None else None
    )
    self._log_state(f"找到块规则: {block_rule_name}")
    matched_rule = self.grammar_rules.get(block_rule_name) if block_rule_name else None
    if matched_rule is None:
        self._log_state(f"未找到匹配的块规则: {start_token}")
        return None
    block_name = matched_rule.name
    end_token = _get_block_end(matched_rule)
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


def collect_line_comments(self, context: ParseContext, block_node: Node) -> None:
    """收集行尾注释（comment → newline），并清除后续空白行"""
    while context.has_more_tokens():
        cur = context.peek_token()
        if cur and cur.type == "comment":
            nxt = context.peek_token(offset=1)
            if nxt and nxt.type == "newline":
                comment_node = Node("Comment")
                comment_node.add_attr("value", cur.content)
                block_node.add_sub_node(comment_node)
                context.advance_token()  # 跳过 comment
                context.advance_token()  # 跳过 newline
                continue
        break
    # 清除后续空白行 vs 下一句之间的空行
    self._skip_tokens(context, tuple(self.skip_types))


def parse_block_body(
    self,
    context: ParseContext,
    block_node: Node,
    rule: GrammarRule,
) -> bool:
    """循环解析句子直到遇到结束符或文件末尾。

    遇到无法匹配的 token 时做逐 token 恢复：
    跳过当前 token 为 ErrorNode，继续下一句。
    """
    end_token = _get_block_end(rule)
    recovery_limit = getattr(self, "_recovery_max_skips", 20)
    skip_count = 0

    while context.has_more_tokens():
        self._skip_tokens(context, tuple(self.skip_types))
        if not context.has_more_tokens():
            break
        self._collect_line_comments(context, block_node)
        if not context.has_more_tokens():
            break

        current = context.peek_token()
        assert current is not None
        if current.type == end_token:
            break

        stmt_node = parse_sentence(self, context)
        if stmt_node is None:
            # 逐 token 恢复：跳过一个 token 为 ErrorNode，继续
            bad = context.peek_token()
            if bad is None:
                break
            if skip_count >= recovery_limit:
                break
            err = Node("Error")
            err.add_attr("raw", bad.content)
            block_node.add_sub_node(err)
            context.advance_token()
            skip_count += 1
            continue
        block_node.add_sub_node(stmt_node)
    return True


def parse_block(
    self,
    context: ParseContext,
    start_token: str | None = None,
    rule: GrammarRule | None = None,
) -> Node | None:
    """解析一个代码块。"""
    if rule is not None:
        matched_rule = rule
        block_name = rule.name
    else:
        resolved = resolve_block_rule(self, start_token)
        if resolved is None:
            return None
        matched_rule, block_name, _ = resolved

    self._log_state(
        f"进入 parse_block, block={block_name}, start_token={start_token}, "
        f"当前 token: {context.peek_token() if context.has_more_tokens() else 'EOF'}"
    )

    if start_token and not consume_start_token(self, context, start_token):
        return None

    block_node = Node(block_name)
    if not parse_block_body(self, context, block_node, matched_rule):
        return None  # 语法错误中断，不产出部分块
    return block_node
