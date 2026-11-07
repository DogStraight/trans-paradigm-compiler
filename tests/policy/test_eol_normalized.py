"""行尾归一门禁：`.gitattributes` 声明的「索引与工作区一律 LF」必须**可执行**。

为什么有它（2026-11-07 实测代价）：`.gitattributes` 早就写着 `* text=auto eol=lf`，判据也
写在注释里（"`git ls-files --eol` 全为 `i/lf w/lf`"），但**没有任何门禁执行它**。结果是本机
工作区里 43 个 `.py` + 59 个文本文件实际是 CRLF（`core.autocrlf=true` + 各工具的写入路径
各自为政）。后果不是"看起来不整齐"，而是**字节级工具当场失效**：
`tools/check_gate_efficacy.py` 按 `newline=""` 读原文件做变异锚点匹配，CRLF 文件里
`...):\n` 匹配不到 → 变异 125 报"锚点未找到（源码已变，清单过时）"，D5 探针整轮红。
**声明过的判据没有门禁，等于没有判据。**
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 防假绿下限：git 至少要看得到这么多跟踪文件（少了说明命令行为变了/跑错了目录）。
MIN_TRACKED = 200


def _eol_rows() -> list[str]:
    """`git ls-files --eol` 的逐行结果（索引/工作区行尾形态 + 属性）。"""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--eol"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, f"git ls-files --eol 失败：{proc.stderr[-500:]}"
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def test_tracked_files_are_lf_in_index_and_worktree() -> None:
    """索引与工作区都必须是 LF（CRLF / mixed 一律红）。"""
    rows = _eol_rows()
    assert len(rows) >= MIN_TRACKED, f"只看到 {len(rows)} 个跟踪文件，判据可能跑错了目录"
    bad = [ln for ln in rows if "w/crlf" in ln or "w/mixed" in ln or "i/crlf" in ln]
    assert not bad, (
        f"{len(bad)} 个跟踪文件不是纯 LF（会让按字节匹配的工具静默失效）。"
        "修法：`git add --renormalize .` 或按 `.gitattributes` 重新检出一遍。\n"
        + "\n".join("  " + ln for ln in bad[:8])
    )
