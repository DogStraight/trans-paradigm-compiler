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
        fr = checker._ctx.memo[os.path.abspath(path)]
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
    """A2 常量宽度求值器（纯函数；常量求值实现在 `checks/_shared.py`）。"""

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
        from grammar.verilog.plugins.checks._shared import const_eval
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_width_text,
        )

        assert const_eval("2*4-1") == 7
        assert const_eval("(8-2)*3") == 18
        assert const_eval("-5+10") == 5
        assert const_eval("10/3") == 3
        assert const_eval("7%3") == 1
        assert eval_width_text("7-1:0") == 7  # 常量折叠后 6:0 → 7 位

    def test_parameterized_returns_none(self):
        from grammar.verilog.plugins.checks._shared import const_eval
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_width_text,
        )

        assert eval_width_text("WIDTH-1:0") is None  # 参数化（B 阶段）
        assert const_eval("WIDTH") is None
        assert const_eval("DATA_W/2") is None
        assert eval_width_text("2*W-1:0") is None

    def test_literal_width(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            literal_width,
        )

        assert literal_width("8'd5") == 8
        assert literal_width("4'b1010") == 4
        assert literal_width("12'hFFF") == 12
        # unsized 最小宽度追踪（Verilator WIDTH 同思路）
        assert literal_width("'hFF") == 8  # 255 需 8 位
        assert literal_width("5") == 3  # 101 需 3 位
        assert literal_width("255") == 8
        assert literal_width("'b101") == 3
        assert literal_width("'o17") == 4  # 15 需 4 位
        assert literal_width("'d255") == 8
        assert literal_width("'shFF") == 8  # signed 前缀同宽
        assert literal_width("0") == 0  # 自适应
        assert literal_width("'0") == 0  # 填充常量自适应
        assert literal_width("'1") == 0
        assert literal_width("'x") == 0
        assert literal_width("'hF_F") == 8  # 0xFF=255 → 8 位（下划线忽略）
        # 含 x/z 位 → 保守 None
        assert literal_width("'hFFx") is None
        assert literal_width("'b1x0") is None
        # 未知形态 → None
        assert literal_width("foo") is None
        assert literal_width("") is None


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
        fr = checker._ctx.memo[os.path.abspath(path)]
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


class TestWidthAssignA4:
    """A4 WIDTH 赋值宽度对比（截断报 W201，扩展/未知不报）。"""

    def _check(self, checker, src_text: str) -> list:
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".sv", delete=False, encoding="utf-8"
        ) as f:
            f.write(src_text)
            path = f.name
        try:
            report = checker.check(path)
            out = []
            for f in report["files"]:
                for d in f["semantic"]:
                    if d.get("code") == "W201":
                        out.append(d["message"])
            return out
        finally:
            os.unlink(path)

    def test_truncation_reported(self, checker):
        """RHS 12 位 → LHS 8 位（assign）报 W201。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [11:0] c;\n"
            "  assign a = c;\n"
            "endmodule\n",
        )
        assert len(msgs) == 1
        assert "12 位" in msgs[0] and "8 位" in msgs[0]

    def test_expansion_not_reported(self, checker):
        """RHS 8 位 → LHS 12 位（扩展）不报。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [11:0] c;\n"
            "  assign c = a;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_blocking_nonblocking(self, checker):
        """阻塞/非阻塞赋值同样检查。"""
        src = (
            "module t (\n"
            "  input wire clk_i,\n"
            "  input wire [7:0] a_i,\n"
            "  output reg [3:0] q_r\n"
            ");\n"
            "  always @(*) q_r = a_i;\n"  # 阻塞：8 → 4 截断
            "  always @(posedge clk_i) q_r <= a_i;\n"  # 非阻塞：8 → 4 截断
            "endmodule\n"
        )
        msgs = self._check(checker, src)
        assert len(msgs) == 2

    def test_equal_width_clean(self, checker):
        """等宽赋值不报。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [7:0] b;\n"
            "  assign a = b;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_expr_rhs(self, checker):
        """表达式 RHS：a + c（max(8,12)=12 > 8）截断。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [3:0] b;\n"
            "  wire [11:0] c;\n"
            "  assign a = a + c;\n"
            "endmodule\n",
        )
        assert len(msgs) == 1

    def test_part_select_lhs(self, checker):
        """位选 LHS：a[3:0] = c（4 < 12）截断。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [11:0] c;\n"
            "  assign a[3:0] = c;\n"
            "endmodule\n",
        )
        assert len(msgs) == 1
        assert "4 位" in msgs[0]

    def test_unsized_rhs_clean(self, checker):
        """unsized 常数最小宽度容纳 / 未知符号 → 不报。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire z;\n"
            "  assign a = 1'b0;\n"  # 1 位扩展不报
            "  assign a = a + 1;\n"  # 1 最小宽 1 位 ≤ 8 → RHS 8 位不报
            "  assign a = '0;\n"  # 填充常量自适应不报
            "  assign a = 5;\n"  # 5 最小宽 3 位 ≤ 8 → 扩展不报
            "  assign a = z;\n"  # z 未声明 → None
            "endmodule\n",
        )
        assert msgs == []

    def test_unsized_truncation_reported(self, checker):
        """unsized 常量最小宽度超出 LHS → 报 W201（Verilator 同思路）。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [3:0] a;\n"
            "  wire [7:0] b;\n"
            "  assign a = 'h1F;\n"  # 31 需 5 位 > 4 → 截断
            "  assign a = 300;\n"  # 300 需 9 位 > 4 → 截断
            "  assign b = 'hFF;\n"  # 255 需 8 位 == 8 → 不报
            "endmodule\n",
        )
        assert len(msgs) == 2
        joined = " | ".join(msgs)
        assert "5 位" in joined and "4 位" in joined  # 'h1F → 截断
        assert "9 位" in joined and "4 位" in joined  # 300 → 截断

    def test_logical_not_width_one(self, checker):
        """`!x` 逻辑非结果 1 位（IEEE 5.5）——1 位 LHS 不报截断。

        对拍 Verilator（V3Width widthBad：!x 结果 1 位）；此前按操作数
        宽误报（picorv32 pcpi_timeout = !pcpi_timeout_counter 4→1）。
        """
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [3:0] cnt;\n"
            "  wire timeout;\n"
            "  assign timeout = !cnt;\n"  # 逻辑非 → 1 位，等宽不报
            "endmodule\n",
        )
        assert msgs == []

    def test_multi_target(self, checker):
        """多目标 assign：c→a 截断 + a→b 截断（b 4 位）共 2 条。"""
        msgs = self._check(
            checker,
            "module t;\n"
            "  wire [7:0] a;\n"
            "  wire [3:0] b;\n"
            "  wire [11:0] c;\n"
            "  assign a = c, b = a;\n"
            "endmodule\n",
        )
        assert len(msgs) == 2
        assert any("a = c" in m for m in msgs)
        assert any("b = a" in m for m in msgs)


class TestWidthEvalParamsB2:
    """B2 参数化宽度求值（符号化常量求值）。"""

    def test_eval_expr_params(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_expr_params,
        )

        assert eval_expr_params("8", {}) == 8  # 纯数字
        assert eval_expr_params("WIDTH-1", {"WIDTH": "8"}) == 7
        assert eval_expr_params("DATA_W/2", {"DATA_W": "16"}) == 8
        assert eval_expr_params("A+B", {"A": "2", "B": "3"}) == 5
        assert eval_expr_params("(W-1)*2", {"W": "8"}) == 14
        assert eval_expr_params("W", {"W": "DATA_W/2", "DATA_W": "16"}) == 8  # 链式
        assert eval_expr_params("X", {}) is None  # 未知标识符
        assert eval_expr_params("WIDTH", {"WIDTH": "8"}) == 8

    def test_eval_width_text_params(self):
        from grammar.verilog.plugins.checks.width_check._width_check import (
            eval_width_text_params,
        )

        assert eval_width_text_params("WIDTH-1:0", {"WIDTH": "8"}) == 8
        assert eval_width_text_params("DATA_W-1:0", {"DATA_W": "16"}) == 16
        assert eval_width_text_params("7:0", {}) == 8  # 纯常量优先
        assert eval_width_text_params("", {}) == 1  # 标量
        assert eval_width_text_params("UNKNOWN-1:0", {}) is None  # 未知参数


class TestWidthParametricB2:
    """B2 集成：参数化宽度的符号求值与 W201。"""

    def _check(self, checker, src_text: str) -> list:
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".sv", delete=False, encoding="utf-8"
        ) as f:
            f.write(src_text)
            path = f.name
        try:
            report = checker.check(path)
            out = []
            for f in report["files"]:
                for d in f["semantic"]:
                    if d.get("code") == "W201":
                        out.append(d["message"])
            return out
        finally:
            os.unlink(path)

    def test_parameterized_width_inferred(self, checker):
        """reg [WIDTH-1:0] q（WIDTH=8）→ 宽度 8；q = 16 位 → 截断报 W201。"""
        msgs = self._check(
            checker,
            "module t #(parameter WIDTH = 8);\n"
            "  reg [WIDTH-1:0] q;\n"
            "  wire [15:0] c;\n"
            "  always @(*) q = c;\n"  # 16 → 8 截断（参数化宽度求值后）
            "endmodule\n",
        )
        assert len(msgs) == 1
        assert "16 位" in msgs[0] and "8 位" in msgs[0]

    def test_parameterized_equal_width_clean(self, checker):
        """参数化等宽赋值不报。"""
        msgs = self._check(
            checker,
            "module t #(parameter WIDTH = 8);\n"
            "  reg [WIDTH-1:0] q;\n"
            "  wire [WIDTH-1:0] a;\n"
            "  always @(*) q = a;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_parameterized_unknown_clean(self, checker):
        """参数无默认值（外部实例化提供）→ 本模块内无法求值 → 保守不报。"""
        msgs = self._check(
            checker,
            "module t #(parameter WIDTH);\n"  # 无默认值
            "  reg [WIDTH-1:0] q;\n"
            "  wire [15:0] c;\n"
            "  always @(*) q = c;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_param_expr_width(self, checker):
        """参数表达式宽度：DATA_W/2 位。"""
        msgs = self._check(
            checker,
            "module t #(parameter DATA_W = 16);\n"
            "  reg [DATA_W/2-1:0] q;\n"  # 8 位
            "  wire [15:0] c;\n"
            "  always @(*) q = c;\n"  # 16 → 8 截断
            "endmodule\n",
        )
        assert len(msgs) == 1
        assert "8 位" in msgs[0]


class TestWidthPortConnB3:
    """B3 跨模块参数传播：实例化点端口连接宽度（覆盖后参数求值）。"""

    def _check_top(self, checker, tmp_path, top_src: str) -> list:
        (tmp_path / "adder.sv").write_text(
            "module adder #(parameter WIDTH = 8) (\n"
            "    input  wire [WIDTH-1:0] a_i,\n"
            "    output wire [WIDTH-1:0] y_o\n"
            ");\n"
            "    assign y_o = a_i;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        top = tmp_path / "top.sv"
        top.write_text(top_src, encoding="utf-8")
        report = checker.check(str(top))
        out = []
        for f in report["files"]:
            for d in f["semantic"]:
                if d.get("code") == "W201":
                    out.append(d["message"])
        return out

    def test_override_shrinks_port(self, checker, tmp_path):
        """覆盖 WIDTH=4：16 位信号连 4 位端口 → 截断报 W201。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [15:0] big_sig;\n"
            "  adder #(.WIDTH(4)) u_adder (\n"
            "    .a_i(big_sig),\n"
            "    .y_o()\n"
            "  );\n"
            "  assign big_sig = 16'd0;\n"
            "endmodule\n",
        )
        assert any("adder.a_i 4 位" in m and "16 位" in m for m in msgs)

    def test_default_param_port(self, checker, tmp_path):
        """无覆盖（WIDTH=8 默认）：16 位连 8 位端口 → 截断。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [15:0] big_sig;\n"
            "  adder u_adder (.a_i(big_sig), .y_o());\n"
            "  assign big_sig = 16'd0;\n"
            "endmodule\n",
        )
        assert any("adder.a_i 8 位" in m and "16 位" in m for m in msgs)

    def test_override_expands_no_report(self, checker, tmp_path):
        """覆盖 WIDTH=16：等宽连接不报。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [15:0] sig;\n"
            "  adder #(.WIDTH(16)) u_adder (.a_i(sig), .y_o());\n"
            "  assign sig = 16'd0;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_caller_param_reference(self, checker, tmp_path):
        """覆盖值引用调用者参数：#(.WIDTH(INNER_W))，INNER_W 来自本文件。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top #(parameter INNER_W = 4);\n"
            "  wire [15:0] big_sig;\n"
            "  adder #(.WIDTH(INNER_W)) u_adder (.a_i(big_sig), .y_o());\n"
            "  assign big_sig = 16'd0;\n"
            "endmodule\n",
        )
        assert any("adder.a_i 4 位" in m and "16 位" in m for m in msgs)

    def test_sized_literal_conn(self, checker, tmp_path):
        """连接字面量：12 位连 8 位端口（无覆盖）→ 截断。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  adder u_adder (.a_i(12'hFFF), .y_o());\n"
            "endmodule\n",
        )
        assert any("adder.a_i 8 位" in m and "12 位" in m for m in msgs)

    def test_ordered_conn_width(self, checker, tmp_path):
        """位置连接按声明序匹配端口：16 位连 8 位端口 → 截断 W201。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [15:0] big_sig;\n"
            "  wire [7:0] out_sig;\n"
            "  adder u_adder (big_sig, out_sig);\n"  # a_i=big_sig, y_o=out_sig
            "  assign big_sig = 16'd0;\n"
            "endmodule\n",
        )
        assert any("adder.a_i 8 位" in m and "16 位" in m for m in msgs)

    def test_ordered_override_param(self, checker, tmp_path):
        """位置连接 + 覆盖参数（#(.WIDTH(4))）：覆盖后端口宽参与判定。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [15:0] big_sig;\n"
            "  wire [3:0] out_sig;\n"
            "  adder #(.WIDTH(4)) u_adder (big_sig, out_sig);\n"
            "  assign big_sig = 16'd0;\n"
            "endmodule\n",
        )
        assert any("adder.a_i 4 位" in m and "16 位" in m for m in msgs)

    def test_ordered_override_expands_clean(self, checker, tmp_path):
        """位置连接 + 覆盖 WIDTH=16：等宽连接不报。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  wire [15:0] sig;\n"
            "  wire [15:0] out_sig;\n"
            "  adder #(.WIDTH(16)) u_adder (sig, out_sig);\n"
            "  assign sig = 16'd0;\n"
            "endmodule\n",
        )
        assert msgs == []

    def test_unsized_literal_conn(self, checker, tmp_path):
        """unsized 常量最小宽度超出端口 → 截断（slang port-width-trunc 同思路）。"""
        msgs = self._check_top(
            checker,
            tmp_path,
            "module top;\n"
            "  adder u_adder (.a_i(300), .y_o());\n"  # 300 需 9 位 > 8 → 截断
            "  adder u_fit (.a_i(5), .y_o());\n"  # 5 需 3 位 ≤ 8 → 不报
            "endmodule\n",
        )
        assert any("adder.a_i 8 位" in m and "9 位" in m for m in msgs)


class TestSelectRangeC1:
    """C1 SELRANGE：位选/下标/切片越界报 W202。"""

    def _codes(self, checker, src_text: str) -> list:
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".sv", delete=False, encoding="utf-8"
        ) as f:
            f.write(src_text)
            path = f.name
        try:
            report = checker.check(path)
            return [
                (d.get("code"), d.get("message"))
                for f in report["files"]
                for d in f["semantic"]
                if d.get("code") == "W202"
            ]
        finally:
            os.unlink(path)

    def test_range_out_of_bounds(self, checker):
        """vec[15:0]（vec [7:0]）→ W202。"""
        diags = self._codes(
            checker,
            "module t;\n"
            "  wire [7:0] vec;\n"
            "  wire [15:0] c;\n"
            "  assign c = vec[15:0];\n"
            "endmodule\n",
        )
        assert len(diags) == 1
        assert "vec[15:0]" in diags[0][1] and "8 位" in diags[0][1]

    def test_index_out_of_bounds(self, checker):
        """vec[8]（8 位）→ W202；vec[7] 合法。"""
        diags = self._codes(
            checker,
            "module t;\n"
            "  wire [7:0] vec;\n"
            "  wire c;\n"
            "  assign c = vec[8];\n"  # 越界
            "  assign c = vec[7];\n"  # 合法
            "endmodule\n",
        )
        assert len(diags) == 1
        assert "vec[8]" in diags[0][1]

    def test_in_bounds_clean(self, checker):
        """范围内位选/反向范围不报。"""
        diags = self._codes(
            checker,
            "module t;\n"
            "  wire [7:0] vec;\n"
            "  wire [7:0] c;\n"
            "  assign c = vec[3:0];\n"  # 范围内
            "  assign c = vec[0:7];\n"  # 反向范围 max=7 合法
            "endmodule\n",
        )
        assert diags == []

    def test_variable_index_clean(self, checker):
        """变量索引（i）保守不报。"""
        diags = self._codes(
            checker,
            "module t (\n"
            "  input wire [3:0] i,\n"
            "  output wire [7:0] o\n"
            ");\n"
            "  wire [7:0] vec;\n"
            "  assign vec = 8'd0;\n"
            "  assign o = vec[i];\n"
            "endmodule\n",
        )
        assert diags == []

    def test_parameterized_base(self, checker):
        """参数化 base 宽度：mem[15]（mem [WIDTH-1:0], WIDTH=8）→ W202。"""
        diags = self._codes(
            checker,
            "module t #(parameter WIDTH = 8);\n"
            "  wire [WIDTH-1:0] mem;\n"
            "  wire c;\n"
            "  assign mem = 8'd0;\n"
            "  assign c = mem[15];\n"  # 越界
            "  assign c = mem[7];\n"  # 合法
            "endmodule\n",
        )
        assert len(diags) == 1
        assert "mem[15]" in diags[0][1]

    def test_slice_bounds(self, checker):
        """切片 vec[0+:8] 合法；vec[4+:8] 越界（4+8>8）。"""
        diags = self._codes(
            checker,
            "module t;\n"
            "  wire [7:0] vec;\n"
            "  wire [7:0] c;\n"
            "  assign vec = 8'd0;\n"
            "  assign c = vec[0+:8];\n"  # 0..7 合法
            "  assign c = vec[4+:8];\n"  # 4..11 越界
            "endmodule\n",
        )
        assert len(diags) == 1
        assert "vec[4+:8]" in diags[0][1]
