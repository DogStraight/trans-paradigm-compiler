"""fidelity.py — 保真度分级（ADR-0006 阶段 5）

规范化程度显式可配（verible token 级保真为参照）：
  - full       完全重排（现状）：AST 渲染重排所有格式
  - keep_blank 保留空行：渲染重排内容，但按源结构位置回插空行
  - indent_only 仅缩进：只重排缩进（世界 B formatter 的 indent pass）

keep_blank 实现（src → out 匹配映射表）：
  1. 源与输出分别提取"非空行序列 + 每个非空行前的空行数"
  2. difflib.SequenceMatcher 求 LCS 匹配块，建立 src 行 → out 行映射
  3. 输出每个非空行前，若其匹配某 src 行 → 回插该 src 行的空行数；
     不匹配（重排区）→ 不保留 renderer 自身产生的空行（0）
  效果：结构重排后，源中相邻结构间的空行在输出对应位置保留，
  且不叠加渲染器产生的空行。
Doc: docs/renderer_architecture.md（保真度分级：keep_blank 空行回插）
"""

from __future__ import annotations

import difflib


def keep_blank_lines(source: str, rendered: str) -> str:
    """把源文本的空行分布回插到渲染输出（结构对应位置）。"""
    src_lines = source.split("\n")
    out_lines = rendered.split("\n")
    if len(src_lines) <= 1 or len(out_lines) <= 1:
        return rendered

    src_seq, src_gaps = _nonblank_with_gaps(src_lines)
    out_seq, _ = _nonblank_with_gaps(out_lines)
    if not src_seq or not out_seq:
        return rendered

    # src → out 匹配映射（LCS 匹配块内一一对应）
    src_to_out: dict[int, int] = {}
    sm = difflib.SequenceMatcher(None, src_seq, out_seq)
    for i, j, size in sm.get_matching_blocks():
        for k in range(size):
            src_to_out[i + k] = j + k

    out_to_src = {j: i for i, j in src_to_out.items()}

    # 还原原始 out 行（含缩进）：按 out 非空行序列找原行
    out_raw: list[str] = []
    cursor = 0
    for line in out_seq:
        while cursor < len(out_lines) and out_lines[cursor].strip() != line:
            cursor += 1
        if cursor < len(out_lines):
            out_raw.append(out_lines[cursor])
            cursor += 1
        else:
            out_raw.append(line)

    result: list[str] = []
    for j, raw in enumerate(out_raw):
        src_i = out_to_src.get(j)
        gap = src_gaps[src_i] if src_i is not None else 0
        for _ in range(gap):
            result.append("")
        result.append(raw)
    return "\n".join(result)


def _nonblank_with_gaps(lines: list[str]) -> tuple[list[str], list[int]]:
    """非空行序列 + 每个非空行前的空行数。"""
    seq: list[str] = []
    gaps: list[int] = []
    cur_gap = 0
    for l in lines:
        if not l.strip():
            cur_gap += 1
        else:
            seq.append(l.strip())
            gaps.append(cur_gap)
            cur_gap = 0
    return seq, gaps
