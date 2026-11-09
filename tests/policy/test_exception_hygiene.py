"""异常卫生门禁（`policy/check_exception_hygiene.py`）的判据。

判据只有两条：宽异常必须写理由（`# noqa: BLE001 — 为什么`）、裸 `except:` 一律红。
本文件证明这两条**真的会响**，并钉住"接进 CI"这件事——否则门禁只是躺在仓库里。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TOOL = ROOT / "policy" / "check_exception_hygiene.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("ceh_under_test", _TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ceh_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _scan_samples(tmp_path: Path, samples: dict[str, str]):
    for name, body in samples.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return _load_tool().scan_paths([tmp_path])


def test_broad_except_without_reason_is_h1(tmp_path: Path) -> None:
    """`except Exception:` 不写理由 → H1。"""
    report = _scan_samples(tmp_path, {"a.py": "try:\n    pass\nexcept Exception:\n    pass\n"})
    assert [f.code for f in report.findings] == ["H1"]


def test_empty_reason_still_h1(tmp_path: Path) -> None:
    """写了 `noqa: BLE001` 但理由为空 → 仍算 H1（形式合规、实质没理由）。"""
    body = "try:\n    pass\nexcept Exception:  # noqa: BLE001 -\n    pass\n"
    report = _scan_samples(tmp_path, {"a.py": body})
    assert [f.code for f in report.findings] == ["H1"]


def test_bare_except_is_h2(tmp_path: Path) -> None:
    """裸 `except:` → H2。"""
    report = _scan_samples(tmp_path, {"a.py": "try:\n    pass\nexcept:\n    pass\n"})
    assert [f.code for f in report.findings] == ["H2"]


def test_narrow_and_justified_are_clean(tmp_path: Path) -> None:
    """收窄类型、或宽异常带真实理由 → 不误报。"""
    samples = {
        "narrow.py": "try:\n    pass\nexcept ValueError:\n    pass\n",
        "justified.py": (
            "try:\n    pass\nexcept Exception:  # noqa: BLE001 — 渲染失败按不可判处理\n    pass\n"
        ),
    }
    assert _scan_samples(tmp_path, samples).findings == []


def test_tool_selftest_passes() -> None:
    """工具自带 `--selftest`（逐码自证）必须绿。"""
    proc = subprocess.run([sys.executable, str(_TOOL), "--selftest"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[-1200:]


def test_repo_is_clean() -> None:
    """本仓库当前无异常卫生违规（有就修或写理由，不许留红）。"""
    proc = subprocess.run([sys.executable, str(_TOOL)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout[-2000:]


def test_tool_is_wired_into_ci() -> None:
    """门禁必须在 CI 里跑，否则只是躺着。"""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "policy/check_exception_hygiene.py" in ci
