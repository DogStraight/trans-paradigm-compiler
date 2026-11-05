"""console.py — 进程级 stdout/stderr 自护（单一实现，替代四处副本）。

为什么有它：Windows 控制台/管道默认 cp1252/GBK，非 ASCII 输出会让**本进程**自己
崩（UnicodeEncodeError）；子进程的 `PYTHONIOENCODING` 只管子进程。`reconfigure`
只影响本进程，比替换 `sys.stdout` 安全。

统一行为（审计 2026-11-05 抽离要求"防抽离时顺手把行为改弱"）：能重配则
`encoding="utf-8", errors="backslashreplace"`——正常输出 UTF-8（CI 日志可读），
极端受限环境下退化为可写转义，且**任何**重配失败都不阻断入口（自护本身不能成为
崩溃点）。工具脚本 `python tools/x.py` 的 `sys.path[0]` 是 `tools/`，调用方需先把
仓库根加进 `sys.path`（各入口已就地做，见 tools/*.py 的 `_REPO_ROOT` 引导）。

Doc: core/README.md
"""

from __future__ import annotations

import sys
from collections.abc import Iterable


def ensure_utf8_stdio(streams: Iterable[object] | None = None) -> None:
    """把本进程的 stdout/stderr（或给定流）重配为 UTF-8 输出（失败静默保持原样）。

    Args:
        streams: 可重的流集合；缺省 = `(sys.stdout, sys.stderr)`。
    """
    targets = (sys.stdout, sys.stderr) if streams is None else streams
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # 已被包装/替换的流（如测试捕获）：保持原样
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # 已关闭/不支持重配的受限环境：自护让位，不让入口因自护而崩
            pass
