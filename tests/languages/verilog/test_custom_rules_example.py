"""自定义规则范例（custom_rules_example）行为测试。

锁两条范例规则的启用行为与默认关语义（范例 = checks/README 双路径实操的
可运行实例；规则码 EX001/EX002，default=false）：

    - EX001（postpass 路径）：非 ANSI 端口声明 → 启用时命中；ANSI 头不报
    - EX002（handler 路径）：parameter integer → 启用时命中；[range] 不报
    - 默认关：不注入启用集（None = 走默认语义）→ 两规则零命中

启用注入走 `ProjectChecker._enabled_rules`（评测同款机制，
见 tests/e2e/eval_check_accuracy.py）。
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

from analyzer.checker import ProjectChecker

NON_ANSI = "module top(a, b);\n    input a;\n    output b;\n    assign b = a;\nendmodule\n"

ANSI = (
    "module top(\n"
    "    input  wire a,\n"
    "    output wire b\n"
    ");\n"
    "    assign b = a;\n"
    "endmodule\n"
)

PARAM_INTEGER = (
    "module top(output [7:0] out);\n"
    "    parameter integer WIDTH = 8;\n"
    "    assign out = WIDTH;\n"
    "endmodule\n"
)

PARAM_RANGE = (
    "module top(output [7:0] out);\n"
    "    parameter [7:0] WIDTH = 8;\n"
    "    assign out = WIDTH;\n"
    "endmodule\n"
)


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _codes(tmp_path, checker, src: str, enabled: list[str] | None) -> list[str]:
    """跑一次 check，返回语义诊断码（enabled=None → 默认语义，不注入）。"""
    f = tmp_path / "top.sv"
    f.write_text(src, encoding="utf-8")
    checker._enabled_rules = list(enabled) if enabled is not None else None
    try:
        report = checker.check(str(f))
    finally:
        checker._enabled_rules = None
    codes: list[str] = []
    for fr in report["files"]:
        codes += [d.get("code") for d in fr["semantic"]]
    return codes


class TestAnsiHeader:
    """EX001 — 非 ANSI 端口声明（postpass 路径）。"""

    def test_non_ansi_reported_when_enabled(self, checker, tmp_path):
        assert "EX001" in _codes(tmp_path, checker, NON_ANSI, ["EX001"])

    def test_ansi_header_clean(self, checker, tmp_path):
        assert "EX001" not in _codes(tmp_path, checker, ANSI, ["EX001"])

    def test_function_params_not_reported(self, checker, tmp_path):
        """函数/任务内旧式参数与模块体端口同节点名但不是模块端口 →
        不报 EX001（防误报回归；先例 _fill_body_ports 同款子树跳过）。"""
        src = (
            "module top;\n"
            "    function MyFunc;\n"
            "        input x;\n"
            "        MyFunc = x;\n"
            "    endfunction\n"
            "endmodule\n"
        )
        assert "EX001" not in _codes(tmp_path, checker, src, ["EX001"])

    def test_default_off(self, checker, tmp_path):
        """默认关（不注入）→ 零命中，诊断面零影响。"""
        assert "EX001" not in _codes(tmp_path, checker, NON_ANSI, None)


class TestParamType:
    """EX002 — parameter integer 类型（handler 路径）。"""

    def test_integer_reported_when_enabled(self, checker, tmp_path):
        codes = _codes(tmp_path, checker, PARAM_INTEGER, ["EX002"])
        assert "EX002" in codes

    def test_range_form_clean(self, checker, tmp_path):
        assert "EX002" not in _codes(tmp_path, checker, PARAM_RANGE, ["EX002"])

    def test_default_off(self, checker, tmp_path):
        assert "EX002" not in _codes(tmp_path, checker, PARAM_INTEGER, None)
