"""tools/check_test_isolation.py 自测：解析/分组/差异判据 + 端到端负例。

工具的价值在于"两档差异"能被报出来——这个性质会静默失效（跑绿了但没在比），
所以这里既测纯函数判据，也用**真起子进程**的负例反证工具不是空转：

负例构造：`test_a_sets_state.py` 往共享 helper 模块写一个模块级标志，
`test_b_needs_state.py` 断言该标志存在。
- 共享进程档：A 先跑并写标志 → B 通过；
- 隔离档：B 独起一个解释器 → 标志不存在 → B 失败；
→ 工具必须报「只在隔离档失败」（隐式跨文件依赖），退出码 1。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOL = _ROOT / "tools" / "check_test_isolation.py"

sys.path.insert(0, str(_ROOT / "tools"))
import check_test_isolation as cti  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.smoke


# ── 纯函数判据 ──────────────────────────────────────────────────────────────

def test_parse_nodeids_keeps_ids_with_spaces_and_brackets() -> None:
    """参数化 id 里可以有空格/方括号——按 "路径.py::" 切，不按空白切。"""
    output = (
        "tests/engine/preprocessor/test_macro_regions.py::test_body_slice_equals_region_content[reg [7:0]]\n"
        "tests/engine/lexer/test_lexer.py::TestNegative::test_timeout_safety_net[module m; endmodule]\n"
        "\n"
        "2 tests collected in 0.03s\n"
        "warning: something\n"
    )
    assert cti._parse_nodeids(output) == [
        "tests/engine/preprocessor/test_macro_regions.py::test_body_slice_equals_region_content[reg [7:0]]",
        "tests/engine/lexer/test_lexer.py::TestNegative::test_timeout_safety_net[module m; endmodule]",
    ]


def test_parse_skips_summary_and_warning_lines() -> None:
    assert cti._parse_nodeids("no tests ran in 0.01s\n") == []


def test_group_chunks_file_then_test() -> None:
    ids = [
        "tests/a/test_one.py::test_1",
        "tests/a/test_one.py::test_2",
        "tests/b/test_two.py::test_1",
    ]
    by_file = cti.group_chunks(ids, "file")
    assert list(by_file) == ["tests/a/test_one.py", "tests/b/test_two.py"]
    assert by_file["tests/a/test_one.py"] == ids[:2]

    by_test = cti.group_chunks(ids, "test")
    assert list(by_test) == ids
    assert all(len(v) == 1 for v in by_test.values())


def test_diff_failures_classifies_both_directions() -> None:
    """两个方向都要报：共享档独有的 = 状态泄漏；隔离档独有的 = 隐式跨文件依赖。"""
    isolated = [cti.ChunkResult("tests/a.py", 1, ("tests/a.py::test_x",), "1 failed")]
    shared = cti.ChunkResult(
        "(共享进程)", 1, ("tests/b.py::test_y",), "1 failed, 10 passed",
    )
    shared_only, isolated_only = cti.diff_failures(isolated, shared)
    assert shared_only == ["tests/b.py::test_y"]
    assert isolated_only == ["tests/a.py::test_x"]


def test_diff_failures_empty_when_both_green() -> None:
    isolated = [cti.ChunkResult("tests/a.py", 0, (), "3 passed")]
    shared = cti.ChunkResult("(共享进程)", 0, (), "3 passed")
    assert cti.diff_failures(isolated, shared) == ([], [])


def test_diff_flags_collection_error_without_failed_lines() -> None:
    """收集/导入期错误没有 FAILED 行——用块名占位，不能静默当成通过。"""
    isolated = [cti.ChunkResult("tests/broken/test_x.py", 2, (), "1 error")]
    shared = cti.ChunkResult("(共享进程)", 0, (), "5 passed")
    shared_only, isolated_only = cti.diff_failures(isolated, shared)
    assert shared_only == []
    assert isolated_only == ["tests/broken/test_x.py"]


def test_abs_target_resolves_against_target_dir_not_cwd(tmp_path: Path) -> None:
    """nodeid 相对 rootdir（目标在仓库外时 rootdir 就是那个目录）——必须按
    候选根解析；直接拼 cwd 会得到 "file or directory not found"（实测踩过）。"""
    f = tmp_path / "test_x.py"
    f.write_text("def test_a():\n    assert True\n", encoding="utf-8")
    roots = [str(_ROOT), str(tmp_path)]
    assert cti._abs_target("test_x.py", roots) == str(f)
    assert cti._abs_target(str(f), roots) == str(f)
    assert cti._abs_nodeid("test_x.py::test_a", roots) == f"{f}::test_a"


def test_abs_target_reports_when_unresolvable(tmp_path: Path) -> None:
    """解析不出来就大声失败（把候选路径写进参数），不静默跳过。"""
    got = cti._abs_target("no_such_file.py", [str(_ROOT), str(tmp_path)])
    assert got.startswith("__NOT_FOUND__")
    assert str(tmp_path) in got


def test_failing_ids_handles_elided_path_form() -> None:
    """目标在 rootdir 之外时短摘要行是 `FAILED ::test_needs - ...`（文件部分被省略）。

    实测踩过：只认 `路径.py::` 的正则会一条也匹配不到 → 失败块被当成"无失败行"
    只报块名，定位信息全丢。
    """
    output = (
        "=========================== short test summary info ===========================\n"
        "FAILED ::test_needs - AssertionError: dep\n"
        "1 failed in 0.14s\n"
    )
    assert cti._failing_ids(output) == ("::test_needs",)
    assert cti._compare_key("::test_needs") == "test_needs"
    assert cti._compare_key("tests/a.py::test_x") == "tests/a.py::test_x"


def test_diff_pairs_elided_ids_across_tiers() -> None:
    """两档都省略时按用例名配对——不能算成"两边各有一个独有失败"。"""
    isolated = [cti.ChunkResult("test_b.py", 1, ("::test_needs",), "1 failed")]
    shared = cti.ChunkResult("(共享进程)", 1, ("::test_needs",), "1 failed")
    assert cti.diff_failures(isolated, shared) == ([], [])


def test_failing_ids_strips_message_tail() -> None:
    """比对必须按 nodeid：异常文本两档可能不同，带着比会把同一失败算成两个。"""
    output = "FAILED tests/a.py::test_x - AssertionError: 不一样的信息\n1 failed in 0.1s\n"
    assert cti._failing_ids(output) == ("tests/a.py::test_x",)


def test_stable_summary_strips_timing() -> None:
    """比对用摘要要去计时——否则每个种子都因耗时不同被判成漂移（实测踩过）。"""
    assert cti._stable_summary("7 passed in 3.25s") == "7 passed"
    assert cti._stable_summary("1 failed, 2 passed in 0.51s (0:00:00)") == "1 failed, 2 passed"
    assert cti._stable_summary("2 passed") == "2 passed"


def _run_tool(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_TOOL), *args],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_hashseed_scan_reports_no_drift_for_stable_target() -> None:
    """种子无关的目标：不得报漂移（假阳性会让这一档失去可信度）。"""
    proc = _run_tool(["--hashseed-scan", "2", "tests/e2e/test_fidelity_cache_key.py"])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert "漂移种子：无" in out, out[-2000:]


def test_hashseed_scan_detects_seed_dependent_target(tmp_path: Path) -> None:
    """真依赖种子的目标：必须报出漂移（工具不是空转）。"""
    (tmp_path / "test_seed_dependent.py").write_text(
        "import os\n\n\ndef test_needs_seed_zero():\n"
        "    assert os.environ.get('PYTHONHASHSEED') == '0'\n",
        encoding="utf-8",
    )
    proc = _run_tool(["--hashseed-scan", "3", str(tmp_path)])
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out[-2000:]
    assert "漂移种子：[1, 2]" in out, out[-2000:]


# ── 端到端负例：工具真的能报出两档差异 ──────────────────────────────────────

def test_compare_reports_isolated_only_failure(tmp_path: Path) -> None:
    (tmp_path / "leak_state.py").write_text("FLAG = False\n", encoding="utf-8")
    (tmp_path / "test_a_sets_state.py").write_text(
        "import leak_state\n\n\ndef test_set():\n    leak_state.FLAG = True\n    assert leak_state.FLAG\n",
        encoding="utf-8",
    )
    (tmp_path / "test_b_needs_state.py").write_text(
        "import leak_state\n\n\ndef test_needs():\n    assert leak_state.FLAG, '依赖 A 写的模块级状态'\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(_TOOL), str(tmp_path), "--compare", "--jobs", "2"],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, f"两档差异未被报出：\n{out}"
    assert "只在隔离档失败" in out, out
    assert "test_b_needs_state.py::test_needs" in out, out


def test_isolated_tier_green_on_real_file() -> None:
    """真实仓库里一个小文件在"独立进程"下全绿（工具主用途的正向验证）。

    只取一个小文件：本用例自身跑在外层 pytest 里，再全量起 35 个子进程会撞
    外层 pytest-timeout（实测）；smoke 全层的隔离档由 nightly 档跑。
    """
    proc = subprocess.run(
        [sys.executable, str(_TOOL), "tests/e2e/test_fidelity_cache_key.py", "--jobs", "1"],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "[隔离档] 1 OK / 0 FAIL" in out, out[-3000:]


# ── nodeid 归一（2026-09-26 发布排练暴露的两条边界）────────────────────────

def test_normalize_id_keeps_case_name_for_outside_repo_path() -> None:
    """仓外路径压成 basename，但**必须保留 `::用例名`**（两档比对的唯一稳定标识）。"""
    assert cti._normalize_id(os.path.join("..", "outside", "test_a.py") + "::test_b") == (
        "test_a.py::test_b"
    )


def test_normalize_id_in_repo_absolute_path_becomes_relative_posix() -> None:
    """仓内绝对路径 → 仓根相对 + 正斜杠（两档写法归一）。"""
    abs_path = str(_ROOT / "tests" / "policy" / "test_x.py")
    assert cti._normalize_id(abs_path + "::test_y") == "tests/policy/test_x.py::test_y"


def test_normalize_id_survives_cross_drive(monkeypatch) -> None:
    """跨盘时 `os.path.relpath` 抛 ValueError——工具不得崩，压 basename 并保留用例名。

    Windows 实测：仓在 E:、pytest tmp_path 在 C: 时 relpath 抛
    `ValueError: path is on mount 'C:', start on mount 'E:'`（原实现未接）。
    """
    def raiser(*_args, **_kwargs):
        raise ValueError("path is on mount 'C:', start on mount 'E:'")

    monkeypatch.setattr(cti.os.path, "relpath", raiser)
    assert cti._normalize_id("C:/tmp/iso/test_a.py::test_b") == "test_a.py::test_b"
