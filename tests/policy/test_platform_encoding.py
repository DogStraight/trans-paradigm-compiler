"""D9 跨平台编码探针测试：逐码自证，不只验证现在绿。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "check_platform_encoding.py"
sys.path.insert(0, str(_ROOT / "tools"))

import check_platform_encoding as cpe  # noqa: E402  # pyright: ignore[reportMissingImports]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """用固定 UTF-8 子进程跑工具。"""
    return subprocess.run(
        [sys.executable, str(_TOOL), *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def _scan_sample(
    tmp_path: Path,
    source: str,
    allow: dict[str, str] | None = None,
) -> cpe.ScanReport:
    """把源码写成单个临时 .py 后走扫描器内部入口。"""
    sample = tmp_path / "sample.py"
    sample.write_text(source, encoding="utf-8")
    return cpe.scan_paths([tmp_path], allow={} if allow is None else allow)


def _codes(report: cpe.ScanReport) -> set[str]:
    """对报告里的检查码去重，便于逐码断言。"""
    return {item.code for item in report.findings}


def test_e1_text_io_without_encoding_is_reported(tmp_path: Path) -> None:
    """E1：open() 与 Path.write_text() 缺 encoding 各命中一次。"""
    report = _scan_sample(
        tmp_path,
        "from pathlib import Path\n"
        "def probe() -> None:\n"
        "    open(\"a.txt\").read()\n"
        "    Path(\"a.txt\").write_text(\"x\")\n",
    )
    e1 = [item for item in report.findings if item.code == "E1"]
    assert len(e1) == 2
    assert all(item.path.endswith("sample.py") for item in e1)


def test_e1_io_open_without_encoding_is_reported(tmp_path: Path) -> None:
    """E1（F4）：`io.open` / `builtins.open` 是内建 open 的等价点分名，必须命中。"""
    report = _scan_sample(
        tmp_path,
        "import builtins\n"
        "import io\n"
        "def probe() -> None:\n"
        "    io.open(\"a.txt\").read()\n"
        "    builtins.open(\"a.txt\").read()\n",
    )
    e1 = [item for item in report.findings if item.code == "E1"]
    assert len(e1) == 2


def test_e1_io_open_binary_is_not_reported(tmp_path: Path) -> None:
    """E1（F4 反例）：io.open 的 mode 位置同内建 open，二进制模式不误报。"""
    report = _scan_sample(
        tmp_path,
        "import io\n"
        "def probe() -> None:\n"
        "    io.open(\"a.bin\", \"rb\")\n",
    )
    assert report.findings == []


def test_e3_e4_fstring_path_is_reported(tmp_path: Path) -> None:
    """E3/E4（F4）：f-string 插值路径 = 字符串化路径，比较/切分都要命中。"""
    report = _scan_sample(
        tmp_path,
        "from pathlib import Path\n"
        "def probe(path: Path) -> bool:\n"
        "    f\"{path}\".split(\"/\")\n"
        "    return f\"{path}/x\" == \"a/b\"\n",
    )
    codes = _codes(report)
    assert "E3" in codes and "E4" in codes


def test_e2_subprocess_text_without_encoding_is_reported(tmp_path: Path) -> None:
    """E2：text=True 的 subprocess.run 缺 encoding 命中。"""
    report = _scan_sample(
        tmp_path,
        "import subprocess\n"
        "def probe() -> None:\n"
        "    subprocess.run([\"echo\"], text=True)\n",
    )
    e2 = [item for item in report.findings if item.code == "E2"]
    assert len(e2) == 1
    assert "subprocess.run()" in e2[0].message


def test_e3_stringified_path_comparison_is_reported(tmp_path: Path) -> None:
    """E3：str(path) 与含分隔符字面量比较必须命中。"""
    report = _scan_sample(
        tmp_path,
        "from pathlib import Path\n"
        "def probe(path: Path) -> bool:\n"
        "    return str(path) == \"a/b\"\n",
    )
    assert "E3" in _codes(report)


def test_e4_literal_separator_path_judgment_is_reported(tmp_path: Path) -> None:
    """E4：p.split("/") 与 "/" in p 都必须命中。"""
    report = _scan_sample(
        tmp_path,
        "def probe(p: str) -> None:\n"
        "    p.split(\"/\")\n"
        "    if \"/\" in p:\n"
        "        print(\"x\")\n",
    )
    e4 = [item for item in report.findings if item.code == "E4"]
    assert len(e4) == 2


def test_known_benign_forms_do_not_create_false_positives(tmp_path: Path) -> None:
    """二进制 open、字符级反斜杠比较、POSIX 归一化都不算违规。"""
    report = _scan_sample(
        tmp_path,
        "from pathlib import Path\n"
        "def probe(path: Path, ch: str) -> None:\n"
        "    open(\"a.bin\", \"rb\")\n"
        "    Path(\"a.bin\").open(\"rb\")\n"
        "    if ch == \"\\\\\\\\\":\n"
        "        print(\"char\")\n"
        "    normalized = path.as_posix()\n"
        "    normalized.split(\"/\")\n",
    )
    assert report.findings == []


def test_allow_entry_is_consumed_or_reported_stale(tmp_path: Path) -> None:
    """ALLOW 命中才被消费；只挂一条不存在的键时必须报 E-ALLOW-STALE。"""
    clean = _scan_sample(tmp_path, "value = 1\n")
    assert clean.findings == []
    assert clean.stale_allows == []

    stale = _scan_sample(
        tmp_path,
        "value = 1\n",
        allow={"ghost.py:E1": "测试腐化条目"},
    )
    assert stale.findings == []
    assert len(stale.stale_allows) == 1


def test_missing_input_root_is_visible_and_exit_2(tmp_path: Path) -> None:
    """输入根缺失必须打印 [告警]，且不能被当成零违规绿掉。"""
    missing = tmp_path / "does_not_exist"
    proc = _run(["--paths", str(missing)])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 2
    assert "[告警]" in out
    assert "输入根不存在" in out


def test_repo_scan_is_clean_and_allow_has_no_stale_entries(tmp_path: Path) -> None:
    """全仓真实扫描 rc==0；JSON 里无 findings / 无 stale / 达到文件数下限。"""
    json_path = tmp_path / "platform_encoding.json"
    proc = _run(["--json", str(json_path)])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "[platform-encoding] ✓" in out

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["scanned_files"] >= cpe.MIN_PY_FILES
    assert payload["findings"] == []
    assert payload["stale_allows"] == []
    assert payload["exit_code"] == 0


def test_selftest_reports_all_four_codes_are_live() -> None:
    """--selftest 必须成功，证明 E1/E2/E3/E4 会响且良性形态不误报。"""
    proc = _run(["--selftest"])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "E1/E2/E3/E4" in out
