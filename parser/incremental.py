"""incremental.py — 同文件增量重解析（0.1.4 块 7 · P1 解析层）。

范围与判据见 `docs/gaps/gap-incremental-parse.md`：只做**单文件、单顶层单元被编辑**的
token 级增量；判不准一律**保守回退全量**（漏失效 = 漏报，宁可慢不可错）。跨文件语义
失效传播 / 常驻 watch 属 v0.2（ROADMAP P3.4），不在本模块。

流程：token 级 diff（公共前缀/后缀）→ 用旧 AST 顶层子节点的 `_tok_span` 定位被改单元
→ 只 `parser.parse(new_tokens[s:e])` 该单元的 token 子集 → 替换顶层 children 的对应项。

API：
    result = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    result.ast              # 新 AST（增量成功 = 同一对象被替换后返回；回退 = 新全量 AST）
    result.tokens_reparsed  # 实际重解析的 token 数（0 = 无变更复用）
    result.fallback         # "" = 增量成功；非空 = 回退原因（结果仍等于全量）

Doc: docs/gaps/gap-incremental-parse.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.define import CHILDREN_FIELD, Node


@dataclass
class ReparseResult:
    """一次增量重解析的结果与统计（`fallback` 非空时 `ast` 是全量结果）。"""

    ast: Node | None
    tokens_total: int
    tokens_reparsed: int
    fallback: str = ""


def _token_key(tok) -> tuple[str, str]:
    """token 比较键：类型 + 文本（行/列随编辑漂移，不参与同一性）。"""
    return (tok.type, tok.content)


def _diff(old: list, new: list) -> tuple[int, int, int]:
    """公共前缀/后缀 → `(prefix, old_end, new_end)`（变更区间 `[prefix, *_end)`）。"""
    n_old, n_new = len(old), len(new)
    pfx = 0
    while pfx < n_old and pfx < n_new and _token_key(old[pfx]) == _token_key(new[pfx]):
        pfx += 1
    sfx = 0
    while (
        sfx < n_old - pfx
        and sfx < n_new - pfx
        and _token_key(old[n_old - 1 - sfx]) == _token_key(new[n_new - 1 - sfx])
    ):
        sfx += 1
    return pfx, n_old - sfx, n_new - sfx


def _children(ast: Node) -> list:
    return list(getattr(ast, CHILDREN_FIELD, []) or [])


def _fallback(parser, tokens: list, reason: str) -> ReparseResult:
    """回退：重解析全量；`ast` 即全量结果，语义与直接 parse 等价。"""
    total = len(tokens)
    return ReparseResult(parser.parse(tokens), total, total, reason)


def _locate_unit(ast: Node, pfx: int, old_end: int) -> tuple[int, int, int] | None:
    """顶层子节点里找**完整覆盖**旧变更区间的单元 → `(下标, 旧起点, 旧终点)`。"""
    for index, child in enumerate(_children(ast)):
        span = getattr(child, "_tok_span", None)
        if not isinstance(span, tuple) or len(span) != 2:
            continue
        start, end = span
        if start < end and start <= pfx and old_end <= end:
            return index, start, end
    return None


def _reparse_unit(parser, new_tokens: list, start: int, end: int) -> Node | None:
    """只解析 `[start, end)` 的 token 子集；必须恰好得到一个顶层单元，否则 None。"""
    sub_ast = parser.parse(new_tokens[start:end])
    if sub_ast is None or getattr(parser, "_parse_truncated", False):
        return None
    children = _children(sub_ast)
    return children[0] if len(children) == 1 else None


def incremental_reparse(
    parser, old_tokens: list, new_tokens: list, old_ast: Node | None
) -> ReparseResult:
    """单文件增量重解析：返回新 AST + 统计；任何判不准的情形回退全量。

    Args:
        parser: 已装载规则/词法的 `Parser`（`parse()` 每次重置内部状态，可复用）。
        old_tokens: 旧源词法结果（与 `old_ast` 同一 token 空间）。
        new_tokens: 新源词法结果（行/列为**新源**绝对坐标）。
        old_ast: 旧源 AST（顶层子节点需带 `_tok_span`，P3.1 span 绑定产物）。
    """
    total = len(new_tokens)
    if old_ast is None or not old_tokens:
        return _fallback(parser, new_tokens, "full:no-previous")
    # 解析期符号门控（C typedef 等）：跨单元解析需要作用域重放，P1 直接回退
    if getattr(parser, "symbol_namespaces", None):
        return _fallback(parser, new_tokens, "full:symbol-gate")

    pfx, old_end, new_end = _diff(old_tokens, new_tokens)
    if pfx == old_end and new_end == pfx:
        return ReparseResult(old_ast, total, 0, "")  # 无变更：复用同一 AST
    if pfx == 0 or old_end >= len(old_tokens):
        return _fallback(parser, new_tokens, "full:edge-change")

    located = _locate_unit(old_ast, pfx, old_end)
    if located is None:
        return _fallback(parser, new_tokens, "full:unit-not-found")
    index, start, end = located
    new_end_abs = end + (len(new_tokens) - len(old_tokens))
    if new_end_abs <= start or new_end_abs > total:
        return _fallback(parser, new_tokens, "full:span-shift")

    new_child = _reparse_unit(parser, new_tokens, start, new_end_abs)
    if new_child is None:
        return _fallback(parser, new_tokens, "full:subparse-failed")
    # 顶层 child 的 span 平移回**新 token 绝对坐标**（嵌套子 span 仍相对子集，P1 不修正：
    # 定位只用顶层 child；多编辑累积修正留 P3.2）
    new_child._tok_span = (start, new_end_abs)
    children = _children(old_ast)
    children[index] = new_child
    setattr(old_ast, CHILDREN_FIELD, children)
    return ReparseResult(old_ast, total, new_end_abs - start, "")
