"""grouping.py — 格式化行分组工具

按 scope 深度 + 视觉连续距离对行分组，是 column_align / inst_port 等
pass 的公共基础设施。避免每个 pass 重复实现同一套分组逻辑。
"""

from __future__ import annotations

from typing import Callable

from .boundary import LineContext


def _first_token(line: str) -> str | None:
    """取行首第一个词（用于匹配）。"""
    stripped = line.lstrip()
    if not stripped:
        return None
    return stripped.split()[0]


def _depth_groups(contexts: list[LineContext]) -> dict[int, list[int]]:
    """按 scope_depth 粗略分组（负深度 = 不参与分组，跳过）。"""
    groups: dict[int, list[int]] = {}
    for i, ctx in enumerate(contexts):
        if ctx.scope_depth < 0:
            continue
        groups.setdefault(ctx.scope_depth, []).append(i)
    return groups


def _needs_break(
    lines: list[str],
    prev: int,
    cur_idx: int,
    match_fn: Callable[[str], bool] | None,
    break_distance: int,
) -> bool:
    """两个匹配行之间是否要断开成两组。

    空行是明确的视觉组边界（ref 端口/声明按空行分组，避免跨组 name 列拉宽）；
    无空行时按两行之间的**匹配行数**超过 break_distance 判定。
    """
    between = lines[prev + 1 : cur_idx]
    if any(not l.strip() for l in between):
        return True
    gap = sum(
        1
        for j in range(prev + 1, cur_idx)
        if _first_token(lines[j]) and (not match_fn or match_fn(lines[j]))
    )
    return gap > break_distance


def _split_by_distance(
    matched: list[int],
    lines: list[str],
    match_fn: Callable[[str], bool] | None,
    break_distance: int,
) -> list[list[int]]:
    """把同一深度内的匹配行按视觉连续距离细分组。"""
    out: list[list[int]] = []
    cur = [matched[0]]
    for k in range(1, len(matched)):
        if _needs_break(lines, matched[k - 1], matched[k], match_fn, break_distance):
            out.append(cur)
            cur = [matched[k]]
        else:
            cur.append(matched[k])
    out.append(cur)
    return out


def group_by_scope(
    lines: list[str],
    contexts: list[LineContext],
    match_fn: Callable[[str], bool] | None = None,
    break_distance: int = 3,
) -> list[list[int]]:
    """按 scope 深度分组 → 再按视觉连续距离细分组。

    Args:
        lines: 原始行列表
        contexts: 对应行的 LineContext 列表
        match_fn: 行匹配函数，返回 True 的行才参与分组
        break_distance: 两组之间的最大间隔行数

    Returns:
        分组列表，每组是行索引列表
    """
    result: list[list[int]] = []
    for _, indices in _depth_groups(contexts).items():
        matched = (
            [i for i in indices if match_fn(lines[i])]
            if match_fn is not None
            else list(indices)
        )
        if len(matched) < 2:
            continue
        result.extend(_split_by_distance(matched, lines, match_fn, break_distance))
    return result


def compute_column_widths(rows: list[list[str]], columns: int) -> list[int]:
    """计算每列的最大宽度。"""
    widths = [0] * columns
    for row in rows:
        for j in range(min(columns, len(row))):
            widths[j] = max(widths[j], len(row[j]))
    return widths
