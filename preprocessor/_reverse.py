"""Macro reversal — restore `` `NAME `` from expanded values.

Uses sync-word restoration (pure-text, no token dependency).
"""

from core.config_registry import declare_cfg

# ── 配置需求（来自 pyv.toml） ──────────────────────────
# preprocessor.reverse
#   #sym:config = [reverse]
#   格式: dict
#     { sync_window_base: int, sync_window_pad: int, offset_tolerance: int }
_reverse_cfg: dict = declare_cfg(
    "preprocessor.reverse",
    {"sync_window_base": 15, "sync_window_pad": 5, "offset_tolerance": 2},
    __name__, "_reverse_cfg",
)


def _restore_lines(
    rendered: str,
    prefix: str,
    restoration_stack: list[dict],
) -> str:
    """同步词验证的宏还原。

    每条记录独立从头扫描，找到 body 后检查前 N 字符内是否有同步词。
    同步词不匹配 → 跳过找下一个 body。
    匹配后替换文本，下一条记录从头扫（已替换的位置不再有 body）。

    参数来自配置 preprocessor.reverse（_macro.toml → [reverse]）。
    """
    sync_window_base = _reverse_cfg.get("sync_window_base", 15)
    sync_window_pad = _reverse_cfg.get("sync_window_pad", 5)
    offset_tolerance = _reverse_cfg.get("offset_tolerance", 2)

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
                window = max(sync_window_base, len(sync) + offset + sync_window_pad)
                before = result[max(0, pos - window) : pos]
                count = 0
                sync_idx = -1
                matched = False
                while True:
                    sync_idx = before.find(sync, sync_idx + 1)
                    if sync_idx < 0:
                        break
                    count += 1
                    if count == sync_nth:
                        real_sync_end = max(0, pos - window) + sync_idx + len(sync)
                        actual_offset = pos - real_sync_end
                        if abs(actual_offset - offset) <= offset_tolerance:
                            matched = True
                            break
                if not matched:
                    pos += 1
                    continue

            # 匹配成功
            result = result[:pos] + f"{prefix}{macro}" + result[pos + len(body) :]
            break

    return result


def protect_and_reverse(
    rendered: str,
    prefix: str = "`",
    restoration_stack: list[dict] | None = None,
) -> str:
    """Reverse macro expansion in rendered output.

    Uses `restoration_stack` for sync-word-based restoration.
    参数 prefix 和容差值来自配置 preprocessor.reverse（_macro.toml → [reverse]）。
    """
    if restoration_stack:
        return _restore_lines(rendered, prefix, restoration_stack)
    return rendered
