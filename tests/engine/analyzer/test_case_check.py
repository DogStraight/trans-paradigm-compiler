"""test_case_check.py — case 完整性检查（case_check 插件，P1.10 分支完整性）。

覆盖：case 无 default 报 CC001、有 default 不报、嵌套 case、casex/casez、
真实语法（case 语句在 always 块内）。
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


class TestCaseCheck:
    def test_case_without_default_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg y;\n"
            "  always @(*) begin\n"
            "    case (sel)\n"
            "      2'b00: y = 1'b0;\n"
            "      2'b01: y = 1'b1;\n"
            "    endcase\n"  # 无 default
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "CC001" in _codes(report)

    def test_case_with_default_clean(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg y;\n"
            "  always @(*) begin\n"
            "    case (sel)\n"
            "      2'b00: y = 1'b0;\n"
            "      2'b01: y = 1'b1;\n"
            "      default: y = 1'b0;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "CC001" not in _codes(report)

    def test_nested_case_both_checked(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] a, b;\n"
            "  reg y;\n"
            "  always @(*) begin\n"
            "    case (a)\n"
            "      2'b00: begin\n"
            "        case (b)\n"  # 内层无 default
            "          2'b00: y = 1'b0;\n"
            "        endcase\n"
            "      end\n"
            "      default: y = 1'b1;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "CC001" in _codes(report)  # 内层 case 无 default

    def test_casex_without_default_reported(self, checker, tmp_path):
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg y;\n"
            "  always @(*) begin\n"
            "    casex (sel)\n"
            "      2'b0?: y = 1'b0;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "CC001" in _codes(report)
