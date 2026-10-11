"""
block_parser.py — 块 & 语句级解析

职责：parse_sentence, _resolve_block_rule, _consume_start_token,
_parse_block_body, parse_block。
Doc: docs/language_walkthrough.md（块规则解析）
"""

from core.define import Node, GrammarRule, Token, block_end_of
from .parser_core import ParseContext
from ._constants import (
    COMMENT_NODE_NAME,
    COMMENT_TOKEN_TYPE,
    NEWLINE_TOKEN_TYPE,
)

# ── 歧义位点 raw 暂缓建树（**引擎内部机制**；契约见 linter/linter_architecture.md） ──
# 位置：语句起点命中 pipeline 注入的"合格位点"（按**精确 (line, column)**），且该起点
# 的所有语句候选都匹配失败（能建树就不 raw ⇒ 真语法错照旧）⇒ 不建树、按位点 region
# 的 **token 下标等式**消费整句，产出带 `_verbatim_text` 的节点；渲染走既有直出
# （`renderer/node_renderer.py` 先查 `_verbatim_text`），**渲染零改动**。
# 节点**无子节点**：属性承载全部信息（否则渲染（不遍历子节点）与分析（iter_children）
# 会形成两套真值）。空位点表 ⇒ 机制关闭（默认零影响）。
RAW_NODE_NAME = "RawStatement"


def _char_offset(source: str, line: int, column: int) -> int:
    """（1-based 行，0-based 列）→ 字符偏移（口径同 `pipeline._token_offsets`）。"""
    starts = [0]
    for ln in source.split("\n"):
        starts.append(starts[-1] + len(ln) + 1)
    if 1 <= line < len(starts):
        return starts[line - 1] + column
    return len(source)


def _verbatim_slice(source: str, first: Token, last: Token) -> str:
    """首/末 token 之间的**源文本切片**（含末 token 全文）——保真直出的唯一来源。"""
    if not source:
        return ""
    lo = _char_offset(source, first.line, first.column)
    hi = _char_offset(source, last.line, last.column) + len(str(last.content))
    return source[lo:hi]


def match_raw_site(self, token: Token | None) -> dict | None:
    """按**精确 (line, column)** 找该 token 的位点；无 → None。

    **无 fallback**：曾有的"同行内第一个 column ≥ 位点列"退化会把列漂移变成**错位
    消费**（消费到别的语句），故删掉——对不上即不 raw，走既有失败路径（不静默）。
    位点表为空（默认）⇒ 恒 None，机制关闭。
    """
    if not self.raw_sites or token is None:
        return None
    line, column = token.line, token.column
    for site in self.raw_sites:
        if line == site.get("line") and column == site.get("column"):
            return site
    return None


def try_raw_sentence(
    self, context: ParseContext, site: dict, block_end_token: str | None = None
) -> Node | None:
    """按位点 region 的 **token 下标等式**消费整句，产出 raw 节点（契约 C）。

    等式（冻结）：`consumed == region` —— 位点 region `[lo, hi]` 的 **token 下标**
    （含 trivia）必须与 parser 实际消费的区间逐位相同：入口 `token_pointer` 必须等于
    `lo`，消费后必须到达 `hi + 1`。**不靠"找结束符"重推边界**（那会引入第二份语句
    结束推导，与 linter 的 `_stmt_ends` 漂移）。不满足（下标错位/超界/块结束符在区间
    内）⇒ 返回 None，交回既有失败路径（**不得静默**）。

    `block_end_token`：所在块体的结束符——区间不得吞掉它（块结束符归父块）。
    """
    tokens = context.tokens
    region = site.get("region")
    if not region or len(region) != 2:
        return None
    lo, hi = int(region[0]), int(region[1])
    start = context.token_pointer
    end = hi + 1
    # 区间等式的前半：位点下标必须与 parser 当前位置逐位一致（两侧 token 流同源）
    if lo != start or end <= start or end > len(tokens):
        return None
    if block_end_token and any(t.type == block_end_token for t in tokens[start:end]):
        return None  # 区间吞掉了块结束符 ⇒ 交给既有失败路径（不静默改判）
    text = _verbatim_slice(self.raw_source, tokens[start], tokens[end - 1])
    if not text.strip():
        return None
    node = Node(RAW_NODE_NAME)
    # 契约 A：无子节点；全部信息走属性（渲染直出 + 分析取证）
    node.add_attr("_verbatim_text", text)
    node.add_attr("_tok_span", (start, end))
    node.add_attr("raw_names", list(site.get("names") or []))
    node.add_attr("raw_line", int(site.get("line", 0)))
    node.add_attr("raw_column", int(site.get("column", 0)))
    # `raw_order`：使用点的 token 流序位（同行先后不能只靠 line 判）。**缺省写 None**
    # （不写 -1）：-1 是"有效的极小序位"，会让"照数比"的判定把合法位点误判为"声明在后"。
    order = site.get("order")
    node.add_attr("raw_order", int(order) if isinstance(order, int) else None)
    node.add_attr("raw_reason", str(site.get("reason", "")))
    node.add_attr("raw_eligible", True)
    # 契约 C 的后半：消费位必须等于 region 上界 +1（逐位相等，不"找到即止"）
    context.token_pointer = end
    if context.token_pointer != hi + 1:
        return None
    # 消费记录（按 (line, column) 去重）：候选回溯会让同一位置被重试多次，
    # 记录是"哪些位点被本轮流采用"的集合语义（pipeline 用它报未重定位数）。
    if not any(
        c["line"] == site.get("line") and c["column"] == site.get("column")
        for c in self._raw_sites_consumed
    ):
        self._raw_sites_consumed.append(
            {
                "line": site.get("line"),
                "column": site.get("column"),
                "names": list(site.get("names") or []),
                "reason": site.get("reason", ""),
                "span": (start, end),
                "text": text,
            }
        )
    self._log_state(
        lambda: f"raw 位点暂缓建树: L{site.get('line')}:{site.get('column')} "
        f"span={start}..{end}"
    )
    return node


def try_raw_at_statement_start(
    self, context: ParseContext, block_end_token: str | None = None
) -> Node | None:
    """语句元素起点兜底：当前位置命中位点（精确行列）才尝试 raw。

    调用点两处（**都必须**）：① `parse_sentence` 的"全部候选失败"之后；② `parse_call`
    的规则调用失败之后（单元素 `@Stmt` 与 `@Stmt*` 迭代项都走它，不经 `parse_sentence`）。
    只在**正常建树失败之后**尝试 ⇒ "能建树就不 raw"（真语法错照旧）。
    """
    site = self.match_raw_site(context.peek_token())
    if site is None:
        return None
    return self.try_raw_sentence(context, site, block_end_token)


def parse_sentence(
    self, context: ParseContext, block_end_token: str | None = None
) -> Node | None:
    """解析一条语句：根据当前 token 选择候选规则并尝试匹配。

    `block_end_token`：所在块体的结束符（`parse_block_body` 传入）——raw 暂缓建树的
    区间**不得**吞掉它（块结束符归父块）。
    """
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

    # 所有候选规则都匹配失败 → raw 位点兜底（机制关闭时恒 None）；仍失败才记现场。
    raw_node = try_raw_at_statement_start(self, context)
    if raw_node is not None:
        return raw_node

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
    end_token = block_end_of(matched_rule)
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


def _make_comment_node(comment_node_name: str, content: str) -> Node:
    """构造注释节点：挂 `_comment` 引擎标记（语言无关——renderer 列表
    容器识别独占行注释用；下划线属性 dump 过滤、normalizer 保留）。"""
    comment_node = Node(comment_node_name)
    comment_node.add_attr("value", content)
    comment_node.add_attr("_comment", True)
    return comment_node


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
                comment_node = _make_comment_node(comment_node_name, cur.content)
                block_node.add_sub_node(comment_node)
                # ADR-0013 单机制：注释已成 Comment 节点（结构序渲染）——
                # 登记 line 通道 seen，防 prepare_production 回溯再吞进
                # _line_comment_anchors（双轨冗余，restore existing_lines
                # 本会跳过已渲染注释，登记后彻底不产生冗余条目）
                self._mark_comment_collected(cur.content, cur.line)
                context.advance_token()  # 跳过 comment
                context.advance_token()  # 跳过 newline
                continue
            if not nxt:
                # 文件尾注释（无 trailing newline）：同样收集，避免
                # parse_sentence 把注释当句子起点而 truncated
                comment_node = _make_comment_node(comment_node_name, cur.content)
                block_node.add_sub_node(comment_node)
                self._mark_comment_collected(cur.content, cur.line)
                context.advance_token()  # 跳过 comment
                continue
        break
    self._skip_tokens(context, tuple(self.skip_types))


def _drain_comments(self, context: ParseContext, block_node: Node) -> None:
    """反复"跳空白 + 收集行尾注释"，直到一轮下来 token 指针没有前进。

    内层终止判据 = 指针未前进（`collect_line_comments` 每收一条注释都会
    消费 comment + newline），故收完一轮后循环再跳一次空白继续尝试。
    """
    while True:
        self._skip_tokens(context, tuple(self.skip_types))
        if not context.has_more_tokens():
            return
        before = context.token_pointer
        self._collect_line_comments(context, block_node)
        if context.token_pointer == before:
            return


def _stop_on_sentence_failure(self, context: ParseContext, end_token) -> None:
    """句子解析失败收口：记录失败现场 + 判定是否"提前停止"。

    仅当仍有未消费 token（非 EOF/非块结束符）时标记 `_parse_truncated`：
    这是语法错误的典型现场——解析无法继续但输入未耗尽。
    """
    self._record_fail_site(
        context,
        rule="sentence",
        reason="sentence parse returned None (block body stop)",
        preserve=True,
    )
    cur = context.peek_token()
    if cur is not None and cur.type != end_token:
        self._parse_truncated = True


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
    end_token = block_end_of(rule)

    while context.has_more_tokens():
        _drain_comments(self, context, block_node)

        if not context.has_more_tokens():
            break

        current = context.peek_token()
        assert current is not None
        if current.type == end_token:
            break

        stmt_node = parse_sentence(self, context, end_token)
        if stmt_node is None:
            _stop_on_sentence_failure(self, context, end_token)
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
