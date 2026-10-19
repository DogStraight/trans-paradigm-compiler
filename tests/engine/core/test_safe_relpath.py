"""跨盘路径显示（Windows C: ↔ E:）——`os.path.relpath` ValueError 不得冒泡成崩溃。

判据：`safe_relpath` 在无法相对化时回退原路径；`tpc check` 文本/HTML 报告对
跨盘文件路径给受控显示（不抛 ValueError）。改前：`_print_file_diags` 直接调
`os.path.relpath` ⇒ CLI traceback。复现：测试里 monkeypatch relpath 抛 ValueError
（模拟 Windows 跨盘；同盘正常）。
"""

import os

import main

from core.utils import safe_relpath


def _cross_drive_error(*_args, **_kwargs):
    raise ValueError("path is on mount 'C:', start on mount 'E:'")


def test_safe_relpath_falls_back_to_original_on_value_error(monkeypatch):
    monkeypatch.setattr(os.path, "relpath", _cross_drive_error)
    assert safe_relpath("C:\\project\\top.c") == "C:\\project\\top.c"


def test_print_file_diags_cross_drive_is_controlled(monkeypatch, capsys):
    monkeypatch.setattr(main.os.path, "relpath", _cross_drive_error)
    diag = {
        "code": "X",
        "message": "controlled",
        "level": "error",
        "range": None,
    }
    count = main._print_file_diags(
        {"path": "C:\\project\\top.c", "syntax": [], "semantic": [diag]}
    )
    out = capsys.readouterr().out
    assert count == 1
    assert "C:\\project\\top.c" in out
    assert "controlled" in out
