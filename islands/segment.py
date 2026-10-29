"""segment.py — token 流 → 岛区间（字符 offset）+ water 判定。

岛来自 `linter.discovery.Discovery` 的 `DiscoveredNode` 树（语法配置推导）；本模块只做
"token 区间 → 字符区间"的换算与 water 判据，不含语言知识。

water（原样保留，不进管线）三种：
1. 未被任何岛节点覆盖的 token（含缩进/空行/注释间空白）；
2. 未识别位点（发现层记录，说明这里没有可解析的语法单元）；
3. 含宏/指令行 token 的节点（宏展开会改原文语义，跳过整节点）。

Doc: islands/README.md
"""

from __future__ import annotations

from core.token_protocol import MACRO_PREFIX
from linter.checker import DiscoveredNode


def line_starts(source: str) -> list[int]:
    """行首字符 offset（1-based 行号索引；兼容 LF/CRLF）。"""
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def token_offsets(source: str, tokens) -> list[int]:
    """每 token 在 `source` 中的起始字符 offset（与 pipeline._token_offsets 同口径）。"""
    starts = line_starts(source)
    return [
        starts[t.line - 1] + t.column
        if 0 <= t.line - 1 < len(starts)
        else -1
        for t in tokens
    ]


def node_span(source: str, tokens, offsets: list[int], node: DiscoveredNode):
    """节点 token 区间 → `(start, end)` 字符区间；无效/空区间返回 None。"""
    if node.start < 0 or node.end <= node.start or node.end > len(tokens):
        return None
    start = offsets[node.start]
    last = offsets[node.end - 1]
    if start < 0 or last < 0:
        return None
    end = last + len(str(tokens[node.end - 1].content))
    return (start, end) if end > start else None


def has_macro(tokens, node: DiscoveredNode) -> bool:
    """节点 token 区间内是否含宏/指令行 token（含 ⇒ 该节点整体落水）。"""
    return any(
        str(t.type).startswith(MACRO_PREFIX) for t in tokens[node.start : node.end]
    )


def line_indent(source: str, offset: int) -> str:
    """`offset` 所在行的行首缩进串（空格/Tab 原样）。"""
    line_start = source.rfind("\n", 0, offset) + 1
    i = line_start
    while i < len(source) and source[i] in (" ", "\t"):
        i += 1
    return source[line_start:i]
