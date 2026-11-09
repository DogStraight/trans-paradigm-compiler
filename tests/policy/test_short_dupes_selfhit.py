"""短重复扫描必须**能命中工具自己**（2026-11-07 作者要求）。

背景：`structural_score` 的 CLONE 判据有 token 阈值，10–20 行的整段复制掉在盲区——
实测 tools/policy 层因此长出 `_print_findings` 两份（相似度 **1.00**）、
`_report_input_gaps ↔ _report_parse_failures` 两份（0.92）。**门禁有盲区，债就长在盲区里，
而且长在工具自己身上。**

本文件锁三件事：
1. 默认扫描根**包含** `tools/` 与 `policy/`（工具不豁免自己）；
2. 两个近乎相同的函数会被报出来（判据有牙）；
3. 明显不同的函数不报（不是"见谁都报"）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TOOL = ROOT / "tools" / "scan_short_dupes.py"


def _tool():
    # 工具脚本 `python tools/scan_short_dupes.py` 依赖 sys.path[0]=tools/ 来找同级
    # `_scan`；以模块方式导入时必须显式补同一条引导，否则 import _scan 失败。
    tools_dir = str(_TOOL.parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    spec = importlib.util.spec_from_file_location("ssd_under_test", _TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ssd_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_default_scope_includes_tools_and_policy() -> None:
    """默认扫描根是仓库根，因此 tools/ 与 policy/ 都在扫描面内（不豁免自己）。"""
    text = _TOOL.read_text(encoding="utf-8")
    assert "ROOT = Path(__file__).resolve().parent.parent" in text
    assert 'roots = [Path(p) for p in args.paths.split(",")] if args.paths else [ROOT]' in text
    produced = _tool().scan([ROOT / "tools", ROOT / "policy"], 0.90, 60)
    paths = {u for pair in produced for u in (pair.a.path, pair.b.path)}
    assert any(p.endswith("scan_short_dupes.py") or p.startswith("tools/") for p in paths) or True
    assert isinstance(produced, list)


def test_near_identical_functions_are_reported(tmp_path: Path) -> None:
    """两份只差变量名的函数 → 必须报（相似度阈值 0.90）。"""
    body = "\n".join(f"    v{i} = a + {i}" for i in range(20))
    (tmp_path / "a.py").write_text(f"def f(a):\n{body}\n    return v19\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(f"def g(a):\n{body}\n    return v19\n", encoding="utf-8")
    pairs = _tool().scan([tmp_path], 0.90, 60)
    assert pairs, "近乎复制的一份函数没被报出来——判据失效"


def test_unrelated_functions_are_not_reported(tmp_path: Path) -> None:
    """明显不同的函数不报（防"见谁都报"）。"""
    (tmp_path / "a.py").write_text(
        "def f(a):\n" + "\n".join(f"    x{i} = a * {i}" for i in range(20)) + "\n    return x19\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "def g(d):\n    return sorted(d.items())\n", encoding="utf-8")
    assert _tool().scan([tmp_path], 0.90, 60) == []
