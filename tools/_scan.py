"""_scan.py — 扫描类工具共用的三件小事（**单一实现**）。

**为什么有它**（2026-11-07，`tools/scan_short_dupes.py` 自扫）：`iter_py_files` 在
`tools/check_platform_encoding.py`、`tools/scan_short_dupes.py`、
`policy/check_exception_hygiene.py` 各有一份，两两相似度 0.14 / 0.24 / 0.47——
**同形发散**（各写各的，比逐字复制更难发现）。抽壳之后连"薄包装"都不许再抄一遍
（`structural_score` 当场报了 +47 的 CLONE），所以连"记录缺口 + 遍历"这一步也放在这里。

> 只放与业务无关的壳；各工具的跳过规则与判定逻辑仍留在自己文件里。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def record_skipped(sink: list[tuple[str, str]], rel: str, reason: str) -> None:
    """登记一处"没纳入扫描"的输入（去重、顺序稳定）。

    缺口必须**可见**：扫不到的东西不许算"干净"（D6 静默降级维度的要求）。
    """
    entry = (rel, reason)
    if entry not in sink:
        sink.append(entry)


def _skip(path: Path, root: Path, skip_dirs: frozenset[str]) -> bool:
    """路径是否落在跳过目录里（按仓库相对层级判定）。"""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return any(part in skip_dirs for part in parts)


def _files_under(base: Path, root: Path, skip_dirs: frozenset[str]) -> list[Path]:
    """单个目录根下的 `.py` 文件（已过滤跳过目录）。"""
    return [p for p in sorted(base.rglob("*.py")) if not _skip(p, root, skip_dirs)]


def iter_py_files(
    roots: list[Path],
    *,
    root: Path,
    skip_dirs: frozenset[str],
    sink: list[tuple[str, str]] | None = None,
    label: Callable[[Path], str] = str,
    follow_files: bool = True,
) -> list[Path]:
    """遍历给定根下的 `.py` 文件，并把"没纳入扫描"的根记进 `sink`。

    Args:
        roots: 扫描根（目录，或 `follow_files=True` 时的单个 `.py`）。
        root: 仓库根（用于相对化与跳过判定）。
        skip_dirs: 任意层级命中即跳过的目录名集合。
        sink: 输入缺口登记表（`None` = 不登记）。
        label: 缺口里展示路径的写法（默认 `str`）。
        follow_files: 根本身是 `.py` 时是否直接纳入。

    Returns:
        去重且稳定排序的文件列表。
    """
    out: list[Path] = []
    for base in roots:
        if not base.exists():
            if sink is not None:
                record_skipped(sink, label(base), "输入根不存在")
            continue
        if base.is_file():
            if follow_files and base.suffix == ".py" and base not in out:
                out.append(base)
            elif sink is not None:
                record_skipped(sink, label(base), "输入不是 .py 文件")
            continue
        out.extend(p for p in _files_under(base, root, skip_dirs) if p not in out)
    return out
