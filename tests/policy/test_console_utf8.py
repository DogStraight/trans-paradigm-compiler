"""cp1252/cp936 场景：控制台自护让中文输出不崩。

背景（审计 2026-11-05 抽离轮 → 2026-11-07 外部证伪 F2）：同一段 reconfigure
自护此前复制在 main / 三个 tools 入口；抽到 `core/console.py` 单点后必须钉住
"行为没被抽弱"。F2 的教训是：只测 `core.console` 的合成调用 **不等于** 引擎入口
真的调用了它——`main.py` 此前只在 `_cmd_fragment` 调自护，`check --tree` 在
cp1252 下直接 UnicodeEncodeError（图树里有 ●/├─）。故判据改为**真跑引擎入口**：

- 子进程 `PYTHONIOENCODING=cp1252` / `cp936` 下 `python main.py check <file> --tree`
  rc=0，且 stdout 是 UTF-8 字节（含 ● 符号）；
- tools 入口在 cp1252 下照常打印中文。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_REF_UART = "tests/e2e/samples/real/ref/ref_uart.v"


def _legacy_console_env(encoding: str) -> dict[str, str]:
    """模拟未开 UTF-8 的 Windows 控制台（PYTHONUTF8=0 + 旧代码页）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = encoding
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
        env=_legacy_console_env("cp1252"),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "中文输出".encode("utf-8") in proc.stdout


@pytest.mark.parametrize("encoding", ["cp1252", "cp936"])
def test_engine_entry_tree_prints_utf8_without_crash(encoding: str):
    """F2：真跑引擎入口（main.py check --tree），旧代码页下不许崩。"""
    proc = subprocess.run(
        [sys.executable, "main.py", "check", _REF_UART, "--tree"],
        cwd=_ROOT,
        env=_legacy_console_env(encoding),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    # 输出被自护重配为 UTF-8：中文/图树符号按 utf-8 字节落盘
    assert "● ref_uart.v".encode("utf-8") in proc.stdout


def test_cp1252_tool_entry_prints_chinese_without_crash():
    """工具侧：抽离后的 tools 入口在 cp1252 下照常打印中文（rc=0）。"""
    proc = subprocess.run(
        [sys.executable, "tools/structural_score.py", "--component", "L"],
        cwd=_ROOT,
        env=_legacy_console_env("cp1252"),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "超额".encode("utf-8") in proc.stdout  # 报告含中文且以 UTF-8 落盘
