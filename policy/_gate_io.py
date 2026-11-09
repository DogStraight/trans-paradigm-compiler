"""_gate_io.py — `policy/` 下门禁脚本共用的输出壳（**单一实现**）。

**为什么有它**（2026-11-07，`tools/scan_short_dupes.py` 扫自己扫出来的）：`check_doc_refs`
与 `check_hardcode` 各有一份 `_print_findings`，相似度 **1.00**（逐字复制）；另有
`_report_input_gaps ↔ _report_parse_failures` 相似度 0.92。`structural_score` 的 CLONE
判据有 token 阈值，十几行的整段复制落在盲区，于是债就长在工具自己身上。

本模块只放**与业务无关的输出/输入缺口壳**。各门禁自己的判定逻辑一条都不进这里——
否则抽出来的就不是"公共壳"，而是新的上帝模块。

> 引用方式：`policy/` 下的脚本以 `python policy/x.py` 运行时 `sys.path[0]` 是 `policy/`，
> 故 `import _gate_io` 直接可用；测试里按文件路径 import 时同理（同目录）。
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Protocol


class Finding(Protocol):
    """门禁 finding 的最小契约（各脚本的 dataclass 都满足它）。"""

    path: str
    line: int
    message: str
    detail: str


def print_findings(title: str, findings: Sequence[Finding]) -> None:
    """按统一格式打印一组 finding（0 条也打印，便于对照前后）。"""
    if not findings:
        print(f"  {title}: 0")
        return
    print(f"  {title}: {len(findings)}")
    for f in findings:
        loc = f"{f.path}:{f.line}"
        suffix = f" — {f.detail}" if f.detail else ""
        print(f"      {loc}: {f.message}{suffix}")


def report_input_gaps(gaps: Sequence[tuple[str, str]], *, strict_label: str) -> int:
    """打印"输入面未纳入扫描"的缺口；有缺口返回 1（供 `--strict-input` 用），否则 0。

    缺口必须**可见**（D6 静默降级维度的要求）：扫不到的东西不能算"干净"。
    """
    if not gaps:
        return 0
    print(f"\n[告警] {len(gaps)} 处输入未纳入扫描（{strict_label} 下为 gate）：")
    for rel, reason in gaps:
        print(f"  {rel}: {reason}")
    return 1


def fail(message: str, code: int = 1) -> int:
    """统一的失败出口（stderr + 退出码），避免各脚本各写一套。"""
    sys.stderr.write(message.rstrip() + "\n")
    return code
