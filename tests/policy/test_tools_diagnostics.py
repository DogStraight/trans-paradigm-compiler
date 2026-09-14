"""tools/ 诊断类工具自测：dump_pipeline_state / check_macro_coverage。

两者都不是门禁——一个打印现场状态（诊断跨语言串味），一个量化已知边界（宏位置
透明性）。但"跑得通 + 关键结论行在"是它们的最低保证：工具坏掉时没人会注意到
（与 `check_gate_efficacy` 的动机同）。判据都尽量贴语义，不贴实现细节。

注：跨语言串味的**回归**在 `tests/engine/core/test_language_switch.py`；这里只
保证"看现场"的工具可用（`--pre` 那条顺带证明修复后方向仍正确）。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
_DUMP = _ROOT / "tools" / "dump_pipeline_state.py"
_COVER = _ROOT / "tools" / "check_macro_coverage.py"

pytestmark = pytest.mark.smoke


def _run(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_dump_pipeline_state_reports_language_state() -> None:
    proc = _run(_DUMP, [])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert "ast=Root" in out, out[-2000:]
    assert "_PIPELINE_SHARED 键" in out and "rules 条数" in out, out[-2000:]


def test_dump_pipeline_state_with_foreign_language_pre() -> None:
    """`--pre grammar/c4` 复现"同进程先跑过别的语言"——修复后 verilog 仍正常。"""
    proc = _run(_DUMP, ["--pre", "grammar/c4"])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert "保真度=0.99" in out, out[-2000:]
    assert "ast=Root" in out, out[-2000:]


def test_check_macro_coverage_runs_and_reports(tmp_path: Path) -> None:
    """小样本：跑得通、报告含覆盖数与失败面分布（非门禁，退出码 0）。"""
    src = tmp_path / "mini.v"
    src.write_text("module m;\n  wire a;\nendmodule\n", encoding="utf-8")
    proc = _run(_COVER, ["--file", str(src)])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert "宏位置覆盖：" in out, out[-2000:]
    assert "失败面（按 token 类型" in out, out[-2000:]
