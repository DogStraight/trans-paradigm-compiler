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
        """wire a（无范围）→ ""（标量；数值 = 1 bit 经 table_width_to_num）。"""
        t = _width_table(
            checker,
            "module t;\n  wire a;\n  assign a = 1'b0;\nendmodule\n",
        )
        assert t["a"] == ""

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
        assert t["q"] == ""  # 标量

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
        assert t["b"] == ""  # 标量

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


class TestWidthEvalA2:
    """A2 常量宽度求值器（纯函数）。"""

    def test_range_width(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_width_text,
        )

        assert eval_width_text("7:0") == 8
        assert eval_width_text("0:7") == 8  # 反向范围 abs
        assert eval_width_text("15:8") == 8
        assert eval_width_text("3") == 4  # 单表达式 [n] = n+1
        assert eval_width_text("") == 1  # 标量

    def test_const_arith(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_const_expr,
            eval_width_text,
        )

        assert eval_const_expr("2*4-1") == 7
        assert eval_const_expr("(8-2)*3") == 18
        assert eval_const_expr("-5+10") == 5
        assert eval_const_expr("10/3") == 3
        assert eval_const_expr("7%3") == 1
        assert eval_width_text("7-1:0") == 7  # 常量折叠后 6:0 → 7 位

    def test_parameterized_returns_none(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_const_expr,
            eval_width_text,
        )

        assert eval_width_text("WIDTH-1:0") is None  # 参数化（B 阶段）
        assert eval_const_expr("WIDTH") is None
        assert eval_const_expr("DATA_W/2") is None
        assert eval_width_text("2*W-1:0") is None

    def test_literal_width(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            literal_width,
        )

        assert literal_width("8'd5") == 8
        assert literal_width("4'b1010") == 4
        assert literal_width("12'hFFF") == 12
        assert literal_width("'hFF") is None  # unsized 自动位宽
        assert literal_width("5") is None  # unsized 自定尺寸


def _all_nodes(ast):
    yield ast
    for ch in ast.iter_children():
        yield from _all_nodes(ch)


def _rhs_widths(checker, src_text: str) -> dict:
    """check 源码，返回 {AssignStmt RHS 文本: 推断宽度}。"""
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w", suffix=".sv", delete=False, encoding="utf-8"
    ) as f:
        f.write(src_text)
        path = f.name
    try:
        checker.check(path)
        fr = checker._memo[os.path.abspath(path)]
        from grammar.verilog.plugins.checks.width_check import _width_check as wc

        table = fr.analyzer._width_table
        out = {}
        for n in _all_nodes(fr.ast):
            if n.node_name == "AssignStmt":
                val = getattr(n, "value", None)
                out[wc.node_text(val)] = wc.infer_expr_width(val, table)
        return out
    finally:
        os.unlink(path)


_SRC_A3 = (
    "module t;\n"
    "  wire [7:0] a;\n"
    "  wire [3:0] b;\n"
    "  wire [11:0] c;\n"
    "  wire [7:0] x;\n"
    "  wire [7:0] y;\n"
    "  assign c = {a, b[3:0]};\n"
    "  assign c = b[0];\n"
    "  assign c = b[3:0];\n"
    "  assign c = {4{a[3:0]}};\n"
    "  assign c = ~a;\n"
    "  assign c = a + b;\n"
    "  assign c = a <= b;\n"
    "  assign c = a << 2;\n"
    "  assign c = x ? a : b;\n"
    "  assign c = 4'd1;\n"
    "  assign c = $signed(a);\n"
    "  assign c = a & b;\n"
    "  assign c = z;\n"
    "endmodule\n"
)


class TestWidthInferA3:
    """A3 表达式宽度推断（AssignStmt RHS 集成）。"""

    def test_infer(self, checker):
        w = _rhs_widths(checker, _SRC_A3)
        assert w["{a,b[3:0]}"] == 12  # 拼接和
        assert w["b[0]"] == 1  # 位选单索引
        assert w["b[3:0]"] == 4  # 位选范围
        assert w["{4{a[3:0]}}"] == 16  # 复制 count×宽
        assert w["~a"] == 8  # 一元同宽
        assert w["a+b"] == 8  # 算术 max
        assert w["a<=b"] == 1  # 比较 1 bit
        assert w["a<<2"] == 8  # 移位 LHS 宽
        assert w["x?a:b"] == 8  # 三目 max
        assert w["4'd1"] == 4  # sized 字面量
        assert w["$signed(a)"] == 8  # 系统函数同宽
        assert w["a&b"] == 8  # 位运算 max
        assert w["z"] is None  # 未知符号保守
