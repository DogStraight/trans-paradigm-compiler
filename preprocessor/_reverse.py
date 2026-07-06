"""Macro reversal — restore `` `NAME `` from expanded values.

Uses sync-word restoration (pure-text, no token dependency).
"""

from typing import Optional


def _restore_lines(
    rendered: str,
    prefix: str,
    restoration_stack: list[dict],
) -> str:
    """同步词验证的宏还原。

    每条记录独立从头扫描，找到 body 后检查前 15 字符内是否有同步词。
    同步词不匹配 → 跳过找下一个 body。
    匹配后替换文本，下一条记录从头扫（已替换的位置不再有 body）。
    """
    result = rendered

    for entry in restoration_stack:
        body = entry["body"]
        macro = entry["macro"]
        sync = entry.get("sync", "")
        sync_nth = entry.get("sync_nth", 1)
        offset = entry.get("offset", 0)

        pos = 0
        while True:
            pos = result.find(body, pos)
            if pos < 0:
                break

            if sync:
                window = max(15, len(sync) + offset + 5)
                before = result[max(0, pos - window):pos]
                count = 0
                sync_idx = -1
                matched = False
                while True:
                    sync_idx = before.find(sync, sync_idx + 1)
                    if sync_idx < 0:
                        break
                    count += 1
                    if count == sync_nth:
                        # 偏移验证：实际偏移 vs 记录偏移，允许 ±2
                        real_sync_end = max(0, pos - window) + sync_idx + len(sync)
                        actual_offset = pos - real_sync_end
                        if abs(actual_offset - offset) <= 2:
                            matched = True
                            break
                if not matched:
                    pos += 1
                    continue

            # 匹配成功
            result = result[:pos] + f"{prefix}{macro}" + result[pos + len(body):]
            break

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
