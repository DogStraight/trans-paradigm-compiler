"""indent.py 缩进重排 pass 测试。

规则：块头行（module/begin/case 等）缩进到 depth-1（与配对 end 对齐），
其余行按 depth 缩进；只改行首空白，token 不丢。
"""

import os
import pytest

from grammar.verilog.plugins.formatter.boundary import LineContext, ScopeKind
from grammar.verilog.plugins.formatter.passes.indent import run_indent_pass

pytestmark = pytest.mark.usefixtures("config_loaded")


def _ind4(s: str) -> int:
    n = 0
    for c in s:
        if c == "\t":
            n += 4
        elif c == " ":
            n += 1
        else:
            break
    return n


def _ctx(depth: int, hdr=None, ftr=None, text: str = "", sst=False, else_hdr=False,
         case_item=False) -> LineContext:
    return LineContext(
        line_number=1,
        text=text,
        scope_depth=depth,
        block_header_of=hdr,
        block_footer_of=ftr,
        single_stmt_header=sst,
        is_else_header=else_hdr,
        is_case_item=case_item,
    )


def _fmt(lines, ctxs, width=4):
    # 给每个 ctx 设正确的 line_number（1-based，indent pass 用行号定位）
    for i, c in enumerate(ctxs):
        c.line_number = i + 1
    return run_indent_pass(list(lines), ctxs, indent_width=width)


def test_basic_depth():
    lines = ["a;", "b;"]
    ctxs = [_ctx(1), _ctx(2)]
    out = _fmt(lines, ctxs)
    assert out[0] == "    a;"
    assert out[1] == "        b;"


def test_block_header_depth_minus_one():
    # 块头行（begin）depth=2 → 缩进 1 级（与 end 对齐）
    out = _fmt(["always @* begin"], [_ctx(2, hdr=ScopeKind.BLOCK)])
    assert out[0] == "    always @* begin"


def test_end_uses_depth():
    # end 行 depth=2（pop 后父级）→ 缩进 2 级，与 begin 对齐
    out = _fmt(["end"], [_ctx(2, ftr=ScopeKind.BLOCK)])
    assert out[0] == "        end"


def test_chained_end_else_begin():
    # end else begin：header+footer，depth=3 → 缩进 2 级（与 end 对齐）
    out = _fmt(["end else begin"], [_ctx(3, hdr=ScopeKind.BLOCK, ftr=ScopeKind.BLOCK)])
    assert out[0] == "        end else begin"


def test_module_header_top_level():
    out = _fmt(["module m;"], [_ctx(1, hdr=ScopeKind.MODULE)])
    assert out[0] == "module m;"


def test_endmodule_top_level():
    out = _fmt(["endmodule"], [_ctx(0, ftr=ScopeKind.MODULE)])
    assert out[0] == "endmodule"


def test_case_and_branch():
    # case depth=3 → 缩进 2；分支 begin depth=4 → 缩进 3
    lines = ["case (x)", "0: begin"]
    ctxs = [_ctx(3, hdr=ScopeKind.CASE), _ctx(4, hdr=ScopeKind.BLOCK)]
    out = _fmt(lines, ctxs)
    assert out[0] == " " * 8 + "case (x)"
    assert out[1] == " " * 12 + "0: begin"  # 3 级


def test_empty_line_kept():
    lines = ["a;", "", "b;"]
    ctxs = [_ctx(1), _ctx(1), _ctx(1)]
    out = _fmt(lines, ctxs)
    assert out[1] == ""


def test_token_preserved():
    """缩进只改行首空白，token 序列不变。"""
    lines = ["    if (a) begin", "        x <= y;", "    end"]
    ctxs = [_ctx(3, hdr=ScopeKind.BLOCK), _ctx(3), _ctx(2, ftr=ScopeKind.BLOCK)]
    out = _fmt(lines, ctxs)
    for orig, new in zip(lines, out):
        assert orig.lstrip() == new.lstrip()


def test_tab_indent_normalized():
    # 原 tab 缩进 → 规范空格
    lines = ["\t\tx = 1;"]
    ctxs = [_ctx(2)]
    out = _fmt(lines, ctxs)
    assert out[0] == "        x = 1;"


def test_ifdef_directive_top_level():
    # ifdef 指令行顶格（不随块 depth 缩进）
    lines = ["`ifdef FOO", "    x = 1;", "`endif"]
    ctxs = [_ctx(2), _ctx(2), _ctx(2)]
    out = _fmt(lines, ctxs)
    assert out[0] == "`ifdef FOO"
    assert out[2] == "`endif"


def test_ifdef_branch_content_uses_depth():
    # ifdef 分支内内容按 depth 缩进
    lines = ["`ifdef FOO", "    wire q;", "`endif"]
    ctxs = [_ctx(1), _ctx(1), _ctx(1)]
    out = _fmt(lines, ctxs)
    assert out[1] == "    wire q;"


def test_ifdef_all_variants_top_level():
    for directive in ("`ifdef", "`ifndef", "`else", "`elsif", "`endif"):
        out = _fmt([f"        {directive} FOO"], [_ctx(3)])
        assert out[0] == f"{directive} FOO"


# ── 单语句体悬挂（if/for/else，无 begin）──

def test_if_single_stmt_body_hanging():
    # `if (X)`（无 begin 单语句头）→ 其单语句体 +1
    lines = ["if (!resetn)", "mem_state <= 0;"]
    ctxs = [_ctx(3, sst=True), _ctx(3)]
    out = _fmt(lines, ctxs)
    assert out[0] == " " * 12 + "if (!resetn)"
    assert out[1] == " " * 16 + "mem_state <= 0;"


def test_for_single_stmt_body_hanging():
    lines = ["for (i = 0; i < n; i = i + 1)", "cpuregs[i] = 0;"]
    ctxs = [_ctx(3, sst=True), _ctx(3)]
    out = _fmt(lines, ctxs)
    assert out[1] == " " * 16 + "cpuregs[i] = 0;"


def test_else_line_not_hanging():
    # `if (A)` 后 `else` 链行不悬挂（与 if 对齐）；else 的单语句体悬挂
    lines = ["if (a)", "else", "b = 1;"]
    ctxs = [_ctx(3, sst=True), _ctx(3, sst=True, else_hdr=True), _ctx(3)]
    out = _fmt(lines, ctxs)
    assert out[1] == " " * 12 + "else"
    assert out[2] == " " * 16 + "b = 1;"


def test_nested_if_both_hanging():
    # `if (A)` 单语句头后 `if (B)`（嵌套）→ +1；`if (B)` 的单语句体再 +1
    lines = ["if (a)", "if (b)", "x = 1;"]
    ctxs = [_ctx(3, sst=True), _ctx(3, sst=True), _ctx(3)]
    out = _fmt(lines, ctxs)
    assert out[1] == " " * 16 + "if (b)"
    assert out[2] == " " * 20 + "x = 1;"


def test_case_item_without_begin_hanging():
    # 无 begin 的 case 分支项（`3'b010:` / `default:`）→ case+1 级
    lines = ["3'b010:", "x = 1;"]
    ctxs = [_ctx(3, case_item=True), _ctx(3)]
    out = _fmt(lines, ctxs)
    assert out[0] == " " * 16 + "3'b010:"


def test_inline_if_body_no_hanging():
    # `if (X) stmt;`（body 同行，sst=False）→ 下一行新 if 不被悬挂
    lines = [
        "if (cpu_state == cpu_state_fetch)  ok = 1;",
        "if (cpu_state == cpu_state_ld_rs1) ok = 1;",
    ]
    ctxs = [_ctx(3), _ctx(3)]
    out = _fmt(lines, ctxs)
    assert out[1] == " " * 12 + "if (cpu_state == cpu_state_ld_rs1) ok = 1;"


# ── 集成测试（真实语法 + 边界扫描，验证 generate 层级 / 悬挂）──

def _fmt_source(src: str):
    from grammar.verilog.plugins.formatter import format_source
    from core.define import DEFAULT_RULES_DIR
    return format_source(src, DEFAULT_RULES_DIR)


def _find(out: list[str], key: str) -> str:
    for line in out:
        if key in line:
            return line
    raise AssertionError(f"未找到包含 {key!r} 的行: {out}")


def test_integration_generate_no_depth():
    """独立 `generate`/`endgenerate` 不贡献缩进层级（匹配单行 generate 风格）。"""
    src = (
        "module m;\n"
        "    generate\n"
        "        if (P) begin : gen\n"
        "            assign x = 1;\n"
        "        end\n"
        "    endgenerate\n"
        "    always @(posedge clk) begin\n"
        "        q <= 1;\n"
        "    end\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    assert _ind4(_find(out, "if (P) begin")) == 4        # generate 内 if begin 1 级
    assert _ind4(_find(out, "assign x = 1")) == 8        # body 2 级
    assert _ind4(_find(out, "endgenerate")) == 4         # 与 generate 同级
    assert _ind4(_find(out, "always @(posedge clk)")) == 4  # module 内 1 级


def test_integration_if_for_single_stmt_body():
    """if/for 无 begin 单语句体悬挂 +1。"""
    src = (
        "module m;\n"
        "    always @(posedge clk) begin\n"
        "        if (!resetn)\n"
        "            q <= 0;\n"
        "        for (i = 0; i < 4; i = i + 1)\n"
        "            r[i] <= 0;\n"
        "    end\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    assert _ind4(_find(out, "if (!resetn)")) == 8
    assert _ind4(_find(out, "q <= 0")) == 12             # if 单语句体 +1
    assert _ind4(_find(out, "r[i] <= 0")) == 12          # for 单语句体 +1


def test_integration_else_aligned():
    """else 与 if 对齐（不悬挂），else 单语句体悬挂。"""
    src = (
        "module m;\n"
        "    always @(posedge clk) begin\n"
        "        if (a)\n"
        "            x <= 1;\n"
        "        else\n"
        "            x <= 2;\n"
        "    end\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    assert _ind4(_find(out, "if (a)")) == 8
    assert _ind4(_find(out, "x <= 1")) == 12
    assert _ind4(_find(out, "else")) == 8                # 与 if 对齐
    assert _ind4(_find(out, "x <= 2")) == 12


def test_integration_token_preserved():
    """格式化后 token 完整（不丢不增）。"""
    src = (
        "module m;\n"
        "    always @(posedge clk) begin\n"
        "        if (a) begin\n"
        "            q <= 1;\n"
        "        end else begin\n"
        "            q <= 0;\n"
        "        end\n"
        "    end\n"
        "endmodule\n"
    )
    out = _fmt_source(src)

    def strip_all(text):
        return "".join("".join(l.split()) for l in text.splitlines())
    assert strip_all(out) == strip_all(src)


def test_integration_multiline_stmt_cont():
    """多行语句续行：语句头行尾无分号 → 续行相对语句头 +1（同语句同级，不累积）。"""
    src = (
        "module m;\n"
        "    always @* begin\n"
        "        is_foo <= is_alu_reg_imm && |{mem_rdata_q[31:25],\n"
        "            mem_rdata_q[14:12],\n"
        "            mem_rdata_q[6:0]};\n"
        "        is_bar <= x;\n"
        "    end\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    assert _ind4(_find(out, "is_foo <=")) == 8            # 语句头 2 级
    assert _ind4(_find(out, "mem_rdata_q[14:12],")) == 12  # 续行 +1
    assert _ind4(_find(out, "mem_rdata_q[6:0]};")) == 12   # 续行同级（不累积）
    assert _ind4(_find(out, "is_bar <=")) == 8            # 新语句头回到 2 级


def test_integration_inst_port_no_cont():
    """实例端口行（`.name(...)`）不参与多行续行（inst_port 对齐）。"""
    src = (
        "module m;\n"
        "    foo u_foo (\n"
        "        .a(a),\n"
        "        .b(b)\n"
        "    );\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    assert _ind4(_find(out, "u_foo (")) == 4
    assert _ind4(_find(out, ".a(a),")) == 8               # 端口行正常 depth（不续行）
    assert _ind4(_find(out, ");")) == 4                    # 结束行不续行


def test_integration_port_list_no_cont():
    """模块端口列表（`);` 前）不参与多行续行。"""
    src = (
        "module m (\n"
        "    input clk,\n"
        "    output reg [31:0] q\n"
        ");\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    # port_dir 品类列对齐可能改变空格，按行首 token 匹配
    assert _ind4(_find(out, "clk,")) == 4
    assert _ind4(_find(out, "output reg")) == 4
    assert _ind4(_find(out, ");")) == 0


def test_integration_ifdef_single_stmt_body():
    """if 单语句头后接 ifdef 块：各分支内容继承悬挂（独立 ifdef pass）。"""
    src = (
        "module m;\n"
        "    always @(posedge clk) begin\n"
        "        if (resetn && wr && rd)\n"
        "`ifdef TESTBUG_001\n"
        "            r[rd ^ 1] <= wdata;\n"
        "`elsif TESTBUG_002\n"
        "            r[rd] <= wdata ^ 1;\n"
        "`else\n"
        "            r[rd] <= wdata;\n"
        "`endif\n"
        "        q <= 1;\n"
        "    end\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    assert _ind4(_find(out, "if (resetn")) == 8
    assert _ind4(_find(out, "r[rd ^ 1]")) == 12       # ifdef 首分支内容悬挂
    assert _ind4(_find(out, "wdata ^ 1")) == 12        # elsif 分支
    assert _ind4(_find(out, "r[rd] <= wdata;")) == 12  # else 分支
    assert _ind4(_find(out, "q <= 1")) == 8            # ifdef 后恢复正常


def test_integration_multiline_ternary_cont():
    """连续赋值 `=` 的三目链续行 +2（ref 风格），末行 `:` 同级。"""
    src = (
        "module m;\n"
        "`ifdef ALTOPS\n"
        "    assign pcpi_rd =\n"
        "        instr_mul ? (a + b) :\n"
        "        instr_mulh ? (a - b) : 1'b0;\n"
        "`else\n"
        "    assign pcpi_rd = 1'b0;\n"
        "`endif\n"
        "endmodule\n"
    )
    out = _fmt_source(src).split("\n")
    # assignment 品类列对齐可能改变空格，按宽松 key 匹配
    assert _ind4(_find(out, "pcpi_rd =")) == 4
    assert _ind4(_find(out, "instr_mul ?")) == 12        # 三目链续行 +2
    assert _ind4(_find(out, "instr_mulh ?")) == 12
    assert _ind4(_find(out, "1'b0;")) == 12              # 末行同级
