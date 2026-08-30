"""test_latch_check.py — 锁存风险检查（latch_check 插件，P1.10 锁存预防）。

覆盖：组合 always 内 if 无 else 报 LC001、有 else 不报、时序 always 内
if 无 else 不报（合法复位写法）、嵌套 if、@* 与电平敏感两种组合形态；
2026-08-29 升级全路径判定后新增：case 无 default / 部分臂赋值 / 先赋值
兜底 / case 全值覆盖不报 / for init 不算锁存。
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

    def test_case_without_default_reported(self, checker, tmp_path):
        """case 无 default：部分臂赋值 → 未覆盖值保持 → 锁存。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg [3:0] y;\n"
            "  always @(*) begin\n"
            "    case (sel)\n"
            "      2'b00: y = 4'd0;\n"
            "      2'b01: y = 4'd1;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" in _codes(report)

    def test_case_full_coverage_without_default_clean(self, checker, tmp_path):
        """case 无 default 但常量值全覆盖（解码器）→ 不报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg [3:0] y;\n"
            "  always @(*) begin\n"
            "    case (sel)\n"
            "      2'b00: y = 4'd0;\n"
            "      2'b01: y = 4'd1;\n"
            "      2'b10: y = 4'd2;\n"
            "      2'b11: y = 4'd3;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_case_with_default_clean(self, checker, tmp_path):
        """case 有 default 且各臂赋值 → 不报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg [3:0] y;\n"
            "  always @(*) begin\n"
            "    case (sel)\n"
            "      2'b00: y = 4'd0;\n"
            "      default: y = 4'd1;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_default_assignment_idiom_clean(self, checker, tmp_path):
        """先兜底赋值（out=0; if..out=..）→ 全路径已赋值，不报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg a, b, y;\n"
            "  always @(*) begin\n"
            "    y = 1'b0;\n"  # 兜底
            "    if (a)\n"
            "      y = b;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_branch_local_temp_reported(self, checker, tmp_path):
        """分支局部临时变量仅单臂赋值 → 未全路径赋值，报（Verilator LATCH
        同语义——临时量保持无害但属同类风险，可 lint_off）。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg a, b, sel, out;\n"
            "  reg tmp;\n"
            "  always @(*) begin\n"
            "    if (sel) begin\n"
            "      tmp = a;\n"
            "      out = tmp;\n"
            "    end else\n"
            "      out = b;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" in _codes(report)

    def test_loop_only_assignment_reported(self, checker, tmp_path):
        """while 循环体内才赋值的信号（边界不可判）→ 可能 0 次执行 → 锁存。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [3:0] y;\n"
            "  reg [3:0] n;\n"
            "  always @(*) begin\n"
            "    while (n < 4)\n"
            "      y = y + 4'd1;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" in _codes(report)

    def test_loop_init_not_latch(self, checker, tmp_path):
        """for init（i=0）必执行 → 循环变量不算锁存；兜底后 sum 不算。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [7:0] sum;\n"
            "  reg [3:0] a;\n"
            "  integer i;\n"
            "  always @(*) begin\n"
            "    sum = 8'd0;\n"
            "    for (i = 0; i < 4; i = i + 1)\n"
            "      sum = sum + a;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_constant_bound_loop_clean(self, checker, tmp_path):
        """for 常量边界（i=0; i<4）可判至少执行一次 → 循环内信号不算锁存。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [3:0] y, tmp;\n"
            "  integer i;\n"
            "  always @(*) begin\n"
            "    for (i = 0; i < 4; i = i + 1) begin\n"
            "      tmp = y;\n"
            "      y = tmp + 4'd1;\n"
            "    end\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_parameter_bound_loop_clean(self, checker, tmp_path):
        """for 参数边界（i < STEPS_AT_ONCE，参数默认 1）→ 至少执行一次不报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  parameter STEPS_AT_ONCE = 1;\n"
            "  reg [3:0] y, tmp;\n"
            "  integer i;\n"
            "  always @(*) begin\n"
            "    for (i = 0; i < STEPS_AT_ONCE; i = i + 1)\n"
            "      tmp = y;\n"
            "    y = tmp;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)

    def test_full_case_attr_clean(self, checker, tmp_path):
        """(* full_case *) case 未列值视为 don't-care（综合语义）→ 不报。"""
        src = tmp_path / "t.sv"
        src.write_text(
            "module t;\n"
            "  reg [1:0] sel;\n"
            "  reg [3:0] y;\n"
            "  always @(*) begin\n"
            "    (* full_case *)\n"
            "    case (sel)\n"
            "      2'b00: y = 4'd0;\n"
            "      2'b01: y = 4'd1;\n"
            "      2'b10: y = 4'd2;\n"
            "    endcase\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        report = checker.check(str(src))
        assert "LC001" not in _codes(report)