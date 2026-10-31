"""incremental.py — 同文件增量重解析（0.1.4 块 7 · P2 片段级）。

范围与判据见 `docs/gaps/gap-incremental-parse.md`。与片段模式同源思路：**语法岛 = 片段**
（岛由语法配置推导，零文件级声明面）；这里把"岛"缩到变更所在的 **AST span 节点**，
按该节点的规则名做片段解析，再并回父节点。

三级执行（逐级保守）：
1. **片段级**：最深覆盖变更的 span 节点、且区间内无注释 → `parser.parse_fragment`；
2. **单元级**：顶层单元整段 `parser.parse`（含注释，沿用 P1）；
3. **全量**：任何判不准（多单元/首尾/符号门控/片段未恰好吃完）→ 全量 parse。

含注释区间也走片段级（实测 tv80 采样编辑逐节点等价，见 gap 档）；注释锚跨片段边界的
形式保证仍欠，靠等价测试盯住，出现不等价即回退单元级。跨文件语义失效传播 / 常驻 watch
属 v0.2（ROADMAP P3.4）。

API：
    result = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    result.ast / result.tokens_reparsed / result.fallback / result.level
    # level: "fragment" / "unit" / "full"（"none" = 无变更复用）

Doc: docs/gaps/gap-incremental-parse.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.define import CHILDREN_FIELD, Node

_Item = tuple[list, int, Node, int, int]


@dataclass
class ReparseResult:
    """一次增量重解析的结果与统计（`fallback` 非空时 `ast` 是全量结果）。"""

    ast: Node | None
    tokens_total: int
    tokens_reparsed: int
    fallback: str = ""
    level: str = "full"  # fragment / unit / full / none


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


def _children(node: Node) -> list:
    return list(getattr(node, CHILDREN_FIELD, []) or [])


def _span(node: Node) -> tuple[int, int] | None:
    span = getattr(node, "_tok_span", None)
    if isinstance(span, tuple) and len(span) == 2 and span[0] < span[1]:
        return span
    return None


#: 修改片占比闸门（经验次优，不是精确成本模型）：小文件更保守（固定开销占比大），
#: 大文件放开到 30%——超过即回退全量（增量收益被摊薄，且并树/一致性风险上升）。
#: 依据：作者估算 30%、模型保守 20%；按文件规模在两者间线性插值，封顶 30%。
_RATIO_MIN = 0.20
_RATIO_MAX = 0.30
_RATIO_RAMP_TOKENS = 20000


def _max_change_ratio(total_tokens: int) -> float:
    """修改片占比阈值：`20% → 30%`（随 token 总量在 20k 处到顶）。"""
    ramp = min(1.0, total_tokens / _RATIO_RAMP_TOKENS)
    return _RATIO_MIN + (_RATIO_MAX - _RATIO_MIN) * ramp


def _fallback(parser, tokens: list, reason: str) -> ReparseResult:
    """回退：重解析全量；`ast` 即全量结果，语义与直接 parse 等价。"""
    total = len(tokens)
    return ReparseResult(parser.parse(tokens), total, total, reason, "full")


def _locate_chain(ast: Node, pfx: int, old_end: int) -> list[_Item]:
    """覆盖旧变更区间的节点链（自顶向下 → 最深）；空表 = 无节点完整覆盖。"""
    chain: list[_Item] = []
    container = _children(ast)
    while True:
        hit = None
        for index, child in enumerate(container):
            span = _span(child)
            if span is not None and span[0] <= pfx and old_end <= span[1]:
                hit = (container, index, child, span[0], span[1])
                break
        if hit is None:
            return chain
        chain.append(hit)
        container = _children(hit[2])


def _splice_node(
    parser, item: _Item, new_tokens: list, level: str, delta: int
) -> tuple[Node, int] | None:
    """对单个节点重解析并替换 → `(新节点, 重解析 token 数)`；判不准 → None。"""
    container, index, node, start, end = item
    new_end = end + delta
    if new_end <= start or new_end > len(new_tokens):
        return None
    if level == "fragment":
        new_node = parser.parse_fragment(new_tokens[start:new_end], node.node_name)
    else:
        sub_ast = parser.parse(new_tokens[start:new_end])
        kids = _children(sub_ast) if sub_ast is not None else []
        new_node = kids[0] if len(kids) == 1 else None
    if new_node is None or getattr(parser, "_parse_truncated", False):
        return None
    new_node._tok_span = (start, new_end)
    container[index] = new_node
    return new_node, new_end - start


def incremental_reparse(
    parser, old_tokens: list, new_tokens: list, old_ast: Node | None
) -> ReparseResult:
    """单文件增量重解析：片段级 → 单元级 → 全量（逐级保守）。

    Args:
        parser: 已装载规则/词法的 `Parser`（`parse()` / `parse_fragment()` 每次重置状态，可复用）。
        old_tokens: 旧源词法结果（与 `old_ast` 同一 token 空间）。
        new_tokens: 新源词法结果（行/列为**新源**绝对坐标）。
        old_ast: 旧源 AST（节点需带 `_tok_span`，P3.1 span 绑定产物）。
    """
    total = len(new_tokens)
    if old_ast is None or not old_tokens:
        return _fallback(parser, new_tokens, "full:no-previous")
    # 解析期符号门控（C typedef 等）：跨单元解析需要作用域重放，本 P2 直接回退
    if getattr(parser, "symbol_namespaces", None):
        return _fallback(parser, new_tokens, "full:symbol-gate")

    pfx, old_end, new_end = _diff(old_tokens, new_tokens)
    if pfx == old_end and new_end == pfx:
        return ReparseResult(old_ast, total, 0, "", "none")  # 无变更：复用同一 AST
    if pfx == 0 or old_end >= len(old_tokens):
        return _fallback(parser, new_tokens, "full:edge-change")

    chain = _locate_chain(old_ast, pfx, old_end)
    if not chain:
        return _fallback(parser, new_tokens, "full:unit-not-found")
    # 大改动闸门：最细候选（chain[-1]）的修改片占比超过阈值 → 回退全量
    _, _, _, frag_start, frag_end = chain[-1]
    frag_tokens = frag_end + (total - len(old_tokens)) - frag_start
    if frag_tokens / max(total, 1) > _max_change_ratio(total):
        return _fallback(parser, new_tokens, "full:too-large")
    delta = total - len(old_tokens)
    for item, level in ((chain[-1], "fragment"), (chain[0], "unit")):
        spliced = _splice_node(parser, item, new_tokens, level, delta)
        if spliced is not None:
            _, reparsed = spliced
            return ReparseResult(old_ast, total, reparsed, "", level)
    return _fallback(parser, new_tokens, "full:subparse-failed")
