"""
block_parser.py — 块 & 语句级解析

职责：parse_sentence, _resolve_block_rule, _consume_start_token,
_parse_block_body, parse_block。
Doc: docs/language_walkthrough.md（块规则解析）
"""

from core.define import Node, GrammarRule
from .parser_core import ParseContext
from ._constants import (
    COMMENT_NODE_NAME,
    COMMENT_TOKEN_TYPE,
    NEWLINE_TOKEN_TYPE,
)


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
    self._log_state(lambda: f"sentence: {self._debug_token_info(context)} candidates={[r.name for r in candidates]}")
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

    # 所有候选规则都匹配失败 → 记录失败现场（供最终报告）+ 简略警告
    rule_hint = ", ".join(r.name for r in candidates[:5])
    if len(candidates) > 5:
        rule_hint += f" ... ({len(candidates)} candidates)"
    self._record_fail_site(
        context,
        rule=rule_hint,
        reason="all sentence candidates failed",
    )
    self._warn(
        f"匹配失败: '{current.content}' Ln {current.line} " f"→ 尝试过: {rule_hint}",
        context=context,
    )
    return None


def _get_block_end(rule: GrammarRule) -> str:
    """从规则提取块结束符（block_end 由 production 首尾字面 token 推导）。"""
    if hasattr(rule, "block_end") and rule.block_end:
        return rule.block_end
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


def _derive_comment_node_name(self, comment_token: str) -> str:
    """从语法树推导注释节点名：production 恰好为 [comment_token] 的规则。

    语法规则名不进引擎代码——verilog 有 [Comment] production=["comment"]，
    推导得 "Comment"；c4 无注释规则时回退 COMMENT_NODE_NAME（注释节点无
    渲染布局，静默跳过——现状行为保持）。
    """
    for name, rule in self.grammar_rules.items():
        prods = getattr(rule, "prods", None) or []
        if prods == [comment_token]:
            return name
    return COMMENT_NODE_NAME


def collect_line_comments(self, context: ParseContext, block_node: Node) -> None:
    """收集行尾注释（comment → newline），挂到 block_node.sub_node 作为注释节点。

    注释节点名从语法树自推导（production == [comment] 的规则）。
    文件尾独立注释（comment 后无 newline，如最后一行是注释且无尾随换行）
    同样收集——否则被当句子起点导致 parse truncated（无害但误报）。
    """
    comment_node_name = _derive_comment_node_name(self, COMMENT_TOKEN_TYPE)
    while context.has_more_tokens():
        cur = context.peek_token()
        if cur and cur.type == COMMENT_TOKEN_TYPE:
            nxt = context.peek_token(offset=1)
            if nxt and nxt.type == NEWLINE_TOKEN_TYPE:
                comment_node = Node(comment_node_name)
                comment_node.add_attr("value", cur.content)
                block_node.add_sub_node(comment_node)
                context.advance_token()  # 跳过 comment
                context.advance_token()  # 跳过 newline
                continue
            if not nxt:
                # 文件尾注释（无 trailing newline）：同样收集，避免
                # parse_sentence 把注释当句子起点而 truncated
                comment_node = Node(comment_node_name)
                comment_node.add_attr("value", cur.content)
                block_node.add_sub_node(comment_node)
                context.advance_token()  # 跳过 comment
                continue
        break
    self._skip_tokens(context, tuple(self.skip_types))


def parse_block_body(
    self,
    context: ParseContext,
    block_node: Node,
    rule: GrammarRule,
) -> bool:
    """循环解析句子直到遇到结束符或文件末尾。

    `parse_sentence` 返回 None 时直接 break，块体解析停止。
    语句匹配失败时直接 break，停止块体解析。
    """
    end_token = _get_block_end(rule)

    while context.has_more_tokens():
        # 反复跳过空白 + 收集注释，直到没有更多注释为止
        while True:
            self._skip_tokens(context, tuple(self.skip_types))
            if not context.has_more_tokens():
                break
            before = context.token_pointer
            self._collect_line_comments(context, block_node)
            if context.token_pointer == before:
                break  # 没有收集到注释，退出内层循环

        if not context.has_more_tokens():
            break

        current = context.peek_token()
        assert current is not None
        if current.type == end_token:
            break

        stmt_node = parse_sentence(self, context)
        if stmt_node is None:
            self._record_fail_site(
                context,
                rule="sentence",
                reason="sentence parse returned None (block body stop)",
                preserve=True,
            )
            # 仅当仍有未消费 token（非 EOF/非块结束符）时标记"提前停止"：
            # 这是语法错误的典型现场——解析无法继续但输入未耗尽。
            cur = context.peek_token()
            if cur is not None and cur.type != end_token:
                self._parse_truncated = True
            break
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
