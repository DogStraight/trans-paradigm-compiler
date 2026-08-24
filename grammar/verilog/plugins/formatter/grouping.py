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
    # 按 scope_depth 粗略分组
    depth_groups: dict[int, list[int]] = {}
    for i, ctx in enumerate(contexts):
        if ctx.scope_depth < 0:
            continue
        depth_groups.setdefault(ctx.scope_depth, []).append(i)

    result: list[list[int]] = []
    for _, indices in depth_groups.items():
        if match_fn is not None:
            matched = [i for i in indices if match_fn(lines[i])]
        else:
            matched = list(indices)
        if len(matched) < 2:
            continue
        # 按 break_distance 细分组
        cur = [matched[0]]
        for k in range(1, len(matched)):
            between = lines[matched[k - 1] + 1:matched[k]]
            # 空行是明确的视觉组边界（ref 端口/声明按空行分组，避免跨组 name 列拉宽）
            if any(not l.strip() for l in between):
                result.append(cur)
                cur = [matched[k]]
                continue
            gap = sum(
                1 for j in range(matched[k - 1] + 1, matched[k])
                if _first_token(lines[j]) and (not match_fn or match_fn(lines[j]))
            )
            if gap > break_distance:
                result.append(cur)
                cur = [matched[k]]
            else:
                cur.append(matched[k])
        if cur:
            result.append(cur)
    return result


def extract_rows(
    lines: list[str],
    indices: list[int],
    extract_fn: Callable[[str], list[str] | None],
) -> tuple[list[list[str]], list[int]]:
    """从行列表中提取语义行。

    Args:
        lines: 原始行列表
        indices: 候选行索引
        extract_fn: 提取函数，接收一行文本返回语义列列表，None 表示跳过

    Returns:
        (rows, valid_indices): 成功提取的行列表和对应的索引
    """
    rows: list[list[str]] = []
    valid_indices: list[int] = []
    for idx in indices:
        cols = extract_fn(lines[idx])
        if cols:
            rows.append(cols)
            valid_indices.append(idx)
    return rows, valid_indices


def compute_column_widths(rows: list[list[str]], columns: int) -> list[int]:
    """计算每列的最大宽度。"""
    widths = [0] * columns
    for row in rows:
        for j in range(min(columns, len(row))):
            widths[j] = max(widths[j], len(row[j]))
    return widths
