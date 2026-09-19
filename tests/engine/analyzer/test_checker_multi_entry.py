"""多入口 check 测试 —— 一次检查覆盖多个顶层文件，共享 module_index。

背景：单元定义的发现范围是**入口文件所在目录 + include 目录**
（`_find_module_file`：先找同名文件，再在该目录内做关键字文本扫描兜底）。
因此跨目录的工程（或顶层文件分布在多个目录）必须一次 check——分别 check
时各自的索引互不可见，对方的单元会报成未知单元。
"""

import builtins
import os

import pytest

from analyzer.checker import ProjectChecker

pytestmark = pytest.mark.usefixtures("config_loaded")


@pytest.fixture
def checker() -> ProjectChecker:
    return ProjectChecker(rules_dir="grammar/verilog")


def _codes(report: dict) -> set[str]:
    return {
        d["code"]
        for f in report.get("files", [])
        for d in f.get("semantic", [])
        if d.get("code")
    }


@pytest.fixture
def project(tmp_path):
    """两个目录：顶层在 `top/`，被实例化的单元定义在 `lib/`。

    用跨目录而非同目录：同目录下的定义会被目录文本扫描兜底找到
    （`_find_module_file` 的第二策略），看不到差异。
    """
    top_dir = tmp_path / "top"
    lib_dir = tmp_path / "lib"
    top_dir.mkdir()
    lib_dir.mkdir()
    top = top_dir / "top.sv"
    top.write_text("module top;\n  b u_b ();\nendmodule\n", encoding="utf-8")
    lib = lib_dir / "other_name.sv"
    lib.write_text("module b;\nendmodule\n", encoding="utf-8")
    return top, lib


def test_single_entry_reports_unknown_unit(checker, project):
    """单入口：跨目录的定义不在搜索范围内 → 被实例化的单元成为未知单元。"""
    top, _ = project
    assert "W101" in _codes(checker.check(str(top)))


def test_same_dir_text_scan_fallback(checker, tmp_path):
    """同目录下文件名与单元名不一致时，目录文本扫描兜底仍能找到定义。

    这是 `_find_module_file` 的第二策略（第一策略是同名文件），它使得
    "文件名 ≠ 单元名"在**同目录**内不成问题——锁住它，避免将来有人
    以为这里只做文件名匹配而把它删掉。
    """
    top = tmp_path / "top.sv"
    top.write_text("module top;\n  b u_b ();\nendmodule\n", encoding="utf-8")
    (tmp_path / "weird_name.sv").write_text(
        "module b;\nendmodule\n", encoding="utf-8"
    )
    report = checker.check(str(top))
    assert "W101" not in _codes(report)
    assert "b" in report["modules"]


def test_multi_entry_sees_each_other(checker, project):
    """多入口：一次 check 共享索引 → 跨目录的未知单元消失。"""
    top, other = project
    report = checker.check([str(top), str(other)])
    assert "W101" not in _codes(report)
    # 两个文件都被纳入本次检查
    assert len(report["files"]) == 2
    assert "b" in report["modules"]


def test_dir_index_built_once(checker, tmp_path, monkeypatch):
    """目录内单元名索引按目录建一次：多个未定义单元不重读整个目录。

    背景（外部审计 performance.file-read-in-loop）：原实现对每个未解析的单元名
    都重读目录内全部文件，N 个未定义单元 = 整目录读 N 遍。诱饵文件不含任何单元
    定义，因此它只可能被"建索引"读到——重复查找一旦回潮，计数就会 > 1。
    """
    (tmp_path / "top.sv").write_text(
        "module top;\n  x1 u1 ();\n  x2 u2 ();\n  x3 u3 ();\nendmodule\n",
        encoding="utf-8",
    )
    decoy = tmp_path / "decoy.sv"
    decoy.write_text("// 无单元定义\n", encoding="utf-8")
    target = os.path.abspath(decoy)

    reads = 0
    real_open = builtins.open

    def counting_open(file, *args, **kwargs):
        nonlocal reads
        if isinstance(file, (str, os.PathLike)) and os.path.abspath(file) == target:
            reads += 1
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)
    report = checker.check(str(tmp_path / "top.sv"))
    assert "W101" in _codes(report)
    assert reads == 1


def test_multi_entry_accepts_str_and_list_equivalently(checker, project):
    """单元素列表与字符串等价（不因入口形态改变行为）。"""
    top, _ = project
    as_str = checker.check(str(top))
    as_list = checker.check([str(top)])
    assert _codes(as_str) == _codes(as_list)
    assert len(as_str["files"]) == len(as_list["files"])


def test_duplicate_entries_not_parsed_twice(checker, project):
    """重复入口共享 seen：不重复 parse，文件数不翻倍。"""
    top, weird = project
    report = checker.check([str(top), str(weird), str(top)])
    assert len(report["files"]) == 2
