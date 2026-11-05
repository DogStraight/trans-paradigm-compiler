"""threshold_sweep 量具自检必须绿（审计 A：防"旋钮变化但在空转"）。"""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_threshold_sweep_selftest_green():
    proc = subprocess.run(
        [sys.executable, "tools/threshold_sweep.py", "--selftest"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-1500:]
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout
