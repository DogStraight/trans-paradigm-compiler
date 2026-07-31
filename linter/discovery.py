"""discovery.py — 发现阶段：token 流 → 自动注册的扁平检查器列表。

把源 token 流"变形"为轻量 AST（DiscoveredNode 列表），每个节点描述
一种被发现的语法结构及其 token 区间。检查阶段据此实例化对应 Checker。

发现策略（决策 1：动态前瞻逐步缩小范围）：
    - 用块边界维护上下文栈（top / module_body / proc_body / gen_body）
    - 在上下文中逐 token 扫描：
        关键字/具体符号触发 → 直接注册（A 类）
        标识符触发 → 上下文过滤 + 下一 token 前瞻消歧（B 类）
    - 注册语句后跳到其 end_case 边界，继续扫描（嵌套语句被自然发现，
      因为 body 区间在后续扫描中会再次命中）
"""

from __future__ import annotations

from core.define import Token

from .checker import (
    CTX_TOP,
    CTX_MODULE_BODY,
    CTX_PROC_BODY,
    CTX_GEN_BODY,
    DiscoveredNode,
)
from .lookahead import LookaheadTable

_TRIVIA = frozenset({"space.fold", "comment", "space", "newline"})

# 块 opener → 上下文
_OPENER_CTX = {
    "keyword.module": CTX_MODULE_BODY,
    "keyword.begin": CTX_PROC_BODY,
    "keyword.function": CTX_PROC_BODY,
    "keyword.task": CTX_PROC_BODY,
    "keyword.generate": CTX_GEN_BODY,
}


class Discovery:
    """发现器：产出自动注册的扁平节点列表。"""

    def __init__(
        self,
        tree: dict,
        block_openers: frozenset[str],
        block_closers: frozenset[str],
        bracket_openers: frozenset[str],
        bracket_closers: frozenset[str],
    ) -> None:
        self._tree = tree
        self._lookahead = LookaheadTable(tree)
        self._block_openers = block_openers
        self._block_closers = block_closers
        self._bracket_openers = bracket_openers
        self._bracket_closers = bracket_closers

    def discover(self, tokens: list[Token]) -> list[DiscoveredNode]:
        """扫描 token 流，返回发现的扁平节点列表。"""
        nodes: list[DiscoveredNode] = []
        ctx_stack: list[str] = [CTX_TOP]
        i = 0
        n = len(tokens)
        while i < n:
            i = self._skip(tokens, i, n)
            if i >= n:
                break
            t = tokens[i]

            if t.type == "newline":
                i += 1
                continue

            # 括号内容整体跳过（如端口列表），避免内部 token 被误判为语句起点
            if t.type in self._bracket_openers:
                i = self._skip_balanced(tokens, i, n)
                continue

            # 块边界 → 上下文切换
            if t.type in self._block_openers:
                ctx_stack.append(_OPENER_CTX.get(t.type, ctx_stack[-1]))
                i += 1
                continue
            if t.type in self._block_closers:
                if len(ctx_stack) > 1:
                    ctx_stack.pop()
                i += 1
                continue

            # 语句发现：上下文 + 前瞻消歧
            ctx = ctx_stack[-1]
            nxt_type = self._next_type(tokens, i + 1, n)
            candidates = self._lookahead.classify(t.type, nxt_type, ctx)
            if candidates:
                rule = candidates[0]
                end = self._statement_end(tokens, i, rule, n)
                if end > i:
                    nodes.append(
                        DiscoveredNode(
                            type="statement",
                            rule=rule,
                            start=i,
                            end=end,
                            context=ctx,
                        )
                    )
                    i = end
                    continue
            i += 1
        return nodes

    # ── 辅助 ────────────────────────────────────

    def _statement_end(self, tokens: list[Token], i: int, rule: str, n: int) -> int:
        """确定语句的粗略边界（end_case 或分号/行尾）。

        单 token 语句（如 NullStmt 的分号）只消费起始 token，
        避免 end_case=["newline"] 在单行文件里延伸吞掉后续语句。
        """
        if self._is_single_token_rule(rule):
            return i + 1
        ec = self._lookahead.end_case(rule)
        if ec:
            return self._skip_to_end(tokens, i, ec, n)
        # 无 end_case → 跳到分号或行尾
        return self._skip_to_statement_end(tokens, i, n)

    def _is_single_token_rule(self, rule: str) -> bool:
        """production 只有单个字面 token（如 NullStmt 的 ';'）。"""
        info = self._tree.get(rule, {})
        prods = info.get("prods", [])
        if len(prods) != 1:
            return False
        first = prods[0]
        if first.get("type") != "token":
            return False
        # 含 "|" 的多 token 候选（如 keyword.case|casex）不算单 token
        return "|" not in first.get("token_type", "")

    def _skip_to_statement_end(self, tokens: list[Token], i: int, n: int) -> int:
        depth = 0
        while i < n:
            t = tokens[i]
            if t.type in self._bracket_openers:
                depth += 1
            elif t.type in self._bracket_closers:
                depth = max(0, depth - 1)
            elif depth == 0 and t.type in (
                "symbol.base.semicolon",
                "newline",
                "keyword.endmodule",
            ):
                return i + 1
            i += 1
        return n

    def _skip_to_end(
        self, tokens: list[Token], i: int, end_set: set[str], n: int
    ) -> int:
        depth = 0
        exclude = {s[1:] for s in end_set if s.startswith("!")}
        positive = {s for s in end_set if not s.startswith("!")}
        if not positive:
            j = self._skip(tokens, i + 1, n)
            return j if j <= n else n
        while i < n:
            t = tokens[i]
            if t.type in exclude:
                i += 1
                continue
            if t.type in positive and depth == 0:
                return i + 1
            if t.type in _TRIVIA:
                i += 1
                continue
            if t.type in self._block_openers:
                depth += 1
            elif t.type in self._block_closers:
                depth = max(0, depth - 1)
            i += 1
        return n

    def _skip_balanced(
        self,
        tokens: list[Token],
        i: int,
        n: int,
    ) -> int:
        """从开括号位置跳过配对的括号内容（含嵌套）。"""
        depth = 1
        i += 1
        while i < n and depth > 0:
            t = tokens[i]
            if t.type in self._bracket_openers:
                depth += 1
            elif t.type in self._bracket_closers:
                depth -= 1
            i += 1
        return i

    @staticmethod
    def _next_type(tokens: list[Token], i: int, n: int) -> str:
        while i < n and tokens[i].type in _TRIVIA:
            i += 1
        return tokens[i].type if i < n else ""

    @staticmethod
    def _skip(tokens: list[Token], i: int, n: int) -> int:
        while i < n and tokens[i].type in _TRIVIA:
            i += 1
        return i
