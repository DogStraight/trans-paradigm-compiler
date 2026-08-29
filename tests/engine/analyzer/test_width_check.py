"""test_width_check.py — 位宽一致性插件（width_check，P1.10 分期）。

阶段 A1：符号宽度表——从符号声明提取宽度表达式文本。
覆盖：类型级范围（wire [7:0] a）/ 无范围标量（=1）/ 多声明符按名对齐 /
参数化宽度原样保留（WIDTH-1:0）/ ANSI 与 body 端口 / integer 固定 32。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _width_table(checker, src_text: str) -> dict:
    """check 一段源码，返回 analyzer 的符号宽度表（A1 产物）。"""
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix=".sv", delete=False, encoding="utf-8"
    ) as f:
        f.write(src_text)
        path = f.name
    try:
        checker.check(path)
        fr = checker._memo[os.path.abspath(path)]
        table = getattr(fr.analyzer, "_width_table", None)
        assert table is not None, "width_check 插件未产出宽度表（postpass 未执行？）"
        return table
    finally:
        os.unlink(path)


class TestSymbolWidthTableA1:
    def test_type_level_range(self, checker):
        """wire [7:0] a → "7:0"（类型级 packed_range）。"""
        t = _width_table(
            checker,
            "module t;\n  wire [7:0] a;\n  assign a = 1'b0;\nendmodule\n",
        )
        assert t["a"] == "7:0"

    def test_scalar_no_range(self, checker):
        """wire a（无范围）→ "1"（标量 1 bit）。"""
        t = _width_table(
            checker,
            "module t;\n  wire a;\n  assign a = 1'b0;\nendmodule\n",
        )
        assert t["a"] == "1"

    def test_multi_declarator_by_name(self, checker):
        """wire [3:0] x, y → 两个都 "3:0"（多声明符共享 decl_node 按名对齐）。"""
        t = _width_table(
            checker,
            "module t;\n  wire [3:0] x, y;\n  assign x = y;\nendmodule\n",
        )
        assert t["x"] == "3:0"
        assert t["y"] == "3:0"

    def test_parameterized_width_kept_raw(self, checker):
        """reg [WIDTH-1:0] q → "WIDTH-1:0"（原样保留，A2 求值）。"""
        t = _width_table(
            checker,
            "module t #(parameter WIDTH = 8);\n"
            "  reg [WIDTH-1:0] q;\n"
            "  always @(*) q = q;\n"
            "endmodule\n",
        )
        assert t["q"] == "WIDTH-1:0"

    def test_ansi_port_width(self, checker):
        """ANSI 端口 input wire [7:0] d → "7:0"。"""
        t = _width_table(
            checker,
            "module t (\n"
            "  input  wire [7:0] d,\n"
            "  output wire       q\n"
            ");\n"
            "  assign q = d;\n"
            "endmodule\n",
        )
        assert t["d"] == "7:0"
        assert t["q"] == "1"

    def test_body_port_width(self, checker):
        """旧式 body 端口：宽度由类型声明符号承载（方向声明=属性，
        类型声明=符号——Body*Decl 不注册符号是设计，见 20_body_ports.toml）。"""
        t = _width_table(
            checker,
            "module t;\n"
            "  input [7:0] a;\n"
            "  output b;\n"
            "  wire [7:0] a;\n"
            "  wire b;\n"
            "  assign b = a;\n"
            "endmodule\n",
        )
        assert t["a"] == "7:0"
        assert t["b"] == "1"

    def test_integer_fixed_32(self, checker):
        """integer i → "32"（固定位宽，语言知识）。"""
        t = _width_table(
            checker,
            "module t;\n  integer i;\n  initial i = 0;\nendmodule\n",
        )
        assert t["i"] == "32"

    def test_reg_range(self, checker):
        """reg [4:0] r → "4:0"。"""
        t = _width_table(
            checker,
            "module t;\n  reg [4:0] r;\n  always @(*) r = r;\nendmodule\n",
        )
        assert t["r"] == "4:0"
