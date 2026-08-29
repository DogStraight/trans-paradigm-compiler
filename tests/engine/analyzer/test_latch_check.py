"""test_latch_check.py — 锁存风险检查（latch_check 插件，P1.10 锁存预防）。

覆盖：组合 always 内 if 无 else 报 LC001、有 else 不报、时序 always 内
if 无 else 不报（合法复位写法）、嵌套 if、@* 与电平敏感两种组合形态。
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
    return {
        d.get("code")
        for f in report["files"]
        for d in f["semantic"]
    }


class TestLatchCheck:
    def test_comb_if_without_else_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg a, b, y;\n"
            "  always @(*) begin\n"
            "    if (a)\n"
            "      y = b;\n"  # 无 else → 锁存
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" in _codes(report)

    def test_comb_if_with_else_clean(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg a, b, y;\n"
            "  always @(*) begin\n"
            "    if (a)\n"
            "      y = b;\n"
            "    else\n"
            "      y = 1'b0;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_timing_always_if_without_else_exempt(self, checker, tmp_path):
        """时序 always 内 if 无 else 是合法复位写法，不报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg clk, rst_n, d, q;\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n)\n"
            "      q <= 1'b0;\n"  # 无 else（复位写法，合法）
            "    else\n"
            "      q <= d;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_level_sensitive_comb_reported(self, checker, tmp_path):
        """电平敏感（非 @*）组合 always 也检查。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg a, b, y;\n"
            "  always @(a or b) begin\n"
            "    if (a)\n"
            "      y = b;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" in _codes(report)

    def test_nested_if_checked(self, checker, tmp_path):
        """嵌套 if：外层有 else、内层无 else → 内层报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg a, b, c, y;\n"
            "  always @(*) begin\n"
            "    if (a) begin\n"
            "      if (b)\n"
            "        y = c;\n"  # 内层无 else
            "    end else\n"
            "      y = 1'b0;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" in _codes(report)