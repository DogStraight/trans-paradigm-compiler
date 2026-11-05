"""cp1252 场景：控制台自护单点（`core/console.py`）让中文输出不崩。

背景（审计 2026-11-05）：同一段 reconfigure 自护此前复制在 main / 三个 tools 入口；
抽到单点后必须钉住"行为没被抽弱"——CI runner 无 PYTHONUTF8、默认 cp1252，中文输出
不能崩。判据 = 子进程 `PYTHONIOENCODING=cp1252` 下（引擎入口与一个 tools 入口）
打印中文均 rc=0 且 stdout 是 UTF-8 字节。
"""

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _cp1252_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"
    return env


def test_cp1252_engine_console_prints_chinese_without_crash():
    """引擎侧：import 单点自护后打印中文（无自护时 UnicodeEncodeError）。"""
    code = (
        "from core.console import ensure_utf8_stdio\n"
        "ensure_utf8_stdio()\n"
        "print('中文输出：cp1252 自护')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_ROOT,
        env=_cp1252_env(),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "中文输出".encode("utf-8") in proc.stdout


def test_cp1252_tool_entry_prints_chinese_without_crash():
    """工具侧：抽离后的 tools 入口在 cp1252 下照常打印中文（rc=0）。"""
    proc = subprocess.run(
        [sys.executable, "tools/structural_score.py", "--component", "L"],
        cwd=_ROOT,
        env=_cp1252_env(),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "超额".encode("utf-8") in proc.stdout  # 报告含中文且以 UTF-8 落盘
