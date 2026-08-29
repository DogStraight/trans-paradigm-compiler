"""test_unused_check.py — 未使用声明检查（unused_check 插件，P1.10 第一优先级）。

覆盖：未使用 wire/reg/parameter 报 UN001、被引用的信号不报、端口不报、
`_` 前缀豁免、真实语法（表达式引用挂 _symbol_ref）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _codes(report):
    out = []
    for f in report["files"]:
        for d in f["semantic"]:
            out.append(d.get("code"))
    return out


class TestUnusedCheck:
    def test_unused_wire_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  wire unused_a;\n"  # 未使用
            "  wire used_b;\n"
            "  assign used_b = 1'b1;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        codes = _codes(report)
        assert "UN001" in codes
        msgs = [
            d["message"]
            for f in report["files"]
            for d in f["semantic"]
            if d.get("code") == "UN001"
        ]
        assert any("unused_a" in m for m in msgs)
        assert not any("used_b" in m for m in msgs)

    def test_unused_reg_and_param_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t #(parameter W = 8);\n"  # W 未使用
            "  reg r_unused;\n"
            "  reg r_used;\n"
            "  always @(*) r_used = r_used;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        msgs = [
            d["message"]
            for f in report["files"]
            for d in f["semantic"]
            if d.get("code") == "UN001"
        ]
        joined = " ".join(msgs)
        assert "W" in joined or "r_unused" in joined
        assert "r_used" not in joined

    def test_port_not_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t (input wire a, output wire y);\n"
            "  assign y = a;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        codes = _codes(report)
        assert "UN001" not in codes  # 端口是接口，不报未使用

    def test_underscore_prefix_exempt(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  wire _intentional;\n"  # _ 前缀豁免
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        codes = _codes(report)
        assert "UN001" not in codes

    def test_used_in_expression_not_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  wire a, b;\n"
            "  wire sum;\n"
            "  assign sum = a + b;\n"  # a/b/sum 都被引用
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        msgs = [
            d["message"]
            for f in report["files"]
            for d in f["semantic"]
            if d.get("code") == "UN001"
        ]
        assert msgs == []
