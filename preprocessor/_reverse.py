"""Macro reversal — restore `` `NAME `` from expanded values.

Uses sync-word restoration (pure-text, no token dependency).
"""

from typing import Optional


def _restore_lines(
    rendered: str,
    prefix: str,
    restoration_stack: list[dict],
) -> str:
    """同步词分片 + 偏移定位的宏还原。

    对每条展开记录：
    1. 在渲染输出中找第 sync_nth 个同步词的位置
    2. 以同步词为左边界，下一个同步词（或 EOF）为右边界分片
    3. 在片内按 offset 附近搜 body，替换为 `NAME
    """
    result = rendered

    for entry in restoration_stack:
        body = entry["body"]
        macro = entry["macro"]
        sync = entry.get("sync", "")
        sync_nth = entry.get("sync_nth", 1)
        offset = entry.get("offset", 0)

        if not sync:
            # 无同步词，简单替换
            pos = result.find(body)
            if pos >= 0:
                result = result[:pos] + f"{prefix}{macro}" + result[pos + len(body):]
            continue

        # 找到第 sync_nth 个同步词
        sync_pos = -1
        for _ in range(sync_nth):
            sync_pos = result.find(sync, sync_pos + 1)
            if sync_pos < 0:
                break

        if sync_pos < 0:
            continue  # 同步词找不到 → 跳过

        # 以同步词为左边界，下一个同步词为右边界
        slice_start = sync_pos  # 从同步词开始
        next_sync = result.find(sync, sync_pos + 1)
        slice_end = next_sync if next_sync >= 0 else len(result)

        # 在片内按 offset 附近搜 body
        search_start = slice_start + len(sync) + offset
        search_end = min(slice_end, search_start + len(body) + 5)
        pos = result.find(body, max(0, search_start - 3), search_end + 3)

        if pos < 0:
            # 降级：在整片中搜索
            pos = result.find(body, slice_start, slice_end)

        if pos < 0:
            continue

        result = result[:pos] + f"{prefix}{macro}" + result[pos + len(body):]

    return result


def protect_and_reverse(
    rendered: str,
    original_source: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
    window: int = 3,
    lexer=None,
    restoration_stack: Optional[list[dict]] = None,
) -> str:
    """Reverse macro expansion in rendered output.

    Uses `restoration_stack` for sync-word-based restoration.
    Falls back to string-based heuristic if no stack provided.
    """
    if restoration_stack:
        return _restore_lines(rendered, prefix, restoration_stack)
    return rendered
