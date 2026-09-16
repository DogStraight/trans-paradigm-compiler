"""column_align 语义列提取与重组——数据破坏回归测试。

保护重点：
  1. 带空格数字字面量 init（`32'h ffff_ffff`）不得把 `ffff_ffff` 误判为 name 而丢真名
  2. 一行多声明/多端口（`input clk, resetn,` / `reg a, b;`）不得丢名字
     （单组提取跳过保留原文；多单元提取 _extract_semantic_multi 参与对齐）
  3. **重组输出**：多声明行的后续声明符以 `, ` 单分隔紧跟（不参与列填充/
     不累积漂移——ref 基准风格 `reg dout, din_0, din_1;`；旧实现逐单元补
     `width+1` 前缀致 226 处漂移，e2e `_strip_all` 抹空白天然失明）
"""

import re

from core.define import DEFAULT_RULES_DIR
from grammar.verilog.plugins.formatter import format_source
from grammar.verilog.plugins.formatter.passes.column_align import (
    _tokenize_bracket_aware,
    _extract_semantic,
    _extract_semantic_multi,
    _is_multidecl,
)

# 漂移形态：逗号后 2+ 空格接标识符（正确重组 = `, ` 单空格）
_DRIFT_RE = re.compile(r",\s{2,}[A-Za-z_$][\w$]*\s*[,;]")


def _fmt(src: str) -> str:
    return format_source(src, DEFAULT_RULES_DIR)


def _extract(line: str):
    """行文本 → 语义列。"""
    toks = _tokenize_bracket_aware(line)
    return _extract_semantic(toks)


def _extract_multi(line: str):
    """行文本 → 多语义单元（多声明拆多单元）。"""
    toks = _tokenize_bracket_aware(line)
    return _extract_semantic_multi(toks)


# ── 数据破坏回归：带空格数字 init 不得丢 name ──

def test_init_number_keeps_name():
    cols = _extract("parameter [31:0] LATCHED_IRQ = 32'h ffff_ffff,")
    assert cols is not None
    assert cols[4] == "LATCHED_IRQ", f"name 被误替换: {cols}"
    assert cols[6] == "= 32'h ffff_ffff", f"init 丢等号/数字: {cols}"


def test_init_number_no_trailing_comma():
    cols = _extract("parameter [31:0] STACKADDR = 32'h ffff_ffff")
    assert cols is not None
    assert cols[4] == "STACKADDR"


def test_init_number_spaced_range():
    cols = _extract("parameter [ 0:0] ENABLE_COUNTERS = 1,")
    assert cols is not None
    assert cols[4] == "ENABLE_COUNTERS"


def test_init_unsized_based():
    cols = _extract("parameter [35:0] TRACE_BRANCH = {4'b 0001, 32'b 0};")
    assert cols is not None
    assert cols[4] == "TRACE_BRANCH"


def test_init_expr_keeps_name():
    cols = _extract("localparam regfile_size = (ENABLE_REGS_16_31 ? 32 : 16) + 4 * ENABLE_IRQ;")
    assert cols is not None
    assert cols[4] == "regfile_size"


def test_init_identifier_rhs_keeps_name():
    cols = _extract("wire dbg_mem_addr = mem_addr;")
    assert cols is not None
    assert cols[4] == "dbg_mem_addr"
    assert cols[6] == "= mem_addr"


def test_assign_keeps_name():
    cols = _extract("assign pcpi_rs1 = reg_op1;")
    assert cols is not None
    assert cols[4] == "pcpi_rs1"
    assert cols[6] == "= reg_op1"


def test_localparam_integer():
    cols = _extract("localparam integer irq_timer = 0;")
    assert cols is not None
    assert cols[4] == "irq_timer"


# ── 数据破坏回归：一行多声明不得丢名字（跳过）──

def test_multidecl_input_ports_skipped():
    # 之前把 `clk` 丢了
    assert _extract("input clk, resetn,") is None


def test_multidecl_reg_skipped():
    assert _extract("reg [63:0] count_cycle, count_instr;") is None


def test_multidecl_wire_skipped():
    assert _extract("wire a, b, c;") is None


def test_multidecl_with_init_skipped():
    assert _extract("reg [3:0] a = 1, b = 2;") is None


# ── 多声明多单元提取（P1.5 多声明品类对齐）──

def test_multi_simple_two_decls():
    units = _extract_multi("reg [7:0] a, b;")
    assert units is not None
    assert len(units) == 2
    # 首单元：类型头 + name + 单元间逗号 term
    assert units[0][1] == "reg"
    assert units[0][3] == "[7:0]"
    assert units[0][4] == "a"
    assert units[0][7] == ","
    # 次单元：无类型头（对齐起点一致）、行尾分号 term、indent 空（不重复缩进）
    assert units[1][0] == ""
    assert units[1][1] == ""
    assert units[1][4] == "b"
    assert units[1][7] == ";"


def test_multi_three_decls_no_init():
    units = _extract_multi("wire [3:0] x, y, z;")
    assert units is not None
    assert len(units) == 3
    names = [u[4] for u in units]
    assert names == ["x", "y", "z"]
    assert [u[7] for u in units] == [",", ",", ";"]


def test_multi_with_init_kept():
    units = _extract_multi("integer clocks=0, running=0, load=0;")
    assert units is not None
    assert len(units) == 3
    assert units[0][4] == "clocks" and units[0][6] == "= 0"
    assert units[1][4] == "running" and units[1][6] == "= 0"
    assert units[2][4] == "load" and units[2][6] == "= 0"


def test_multi_input_ports():
    units = _extract_multi("input clk, resetn,")
    assert units is not None
    assert len(units) == 2
    assert units[0][4] == "clk" and units[0][7] == ","
    assert units[1][4] == "resetn" and units[1][7] == ","


def test_multi_shared_type_header_first_only():
    units = _extract_multi("output reg [31:0] mem_addr, mem_wdata;")
    assert units is not None
    assert len(units) == 2
    # 类型头（first/opt_type/opt_range）只挂首单元
    assert units[0][1] == "output"
    assert units[0][2] == "reg"
    assert units[0][3] == "[31:0]"
    assert units[1][1] == "" and units[1][2] == "" and units[1][3] == ""


def test_multi_single_decl_returns_one_group():
    units = _extract_multi("reg [4:0] reg_sh;")
    assert units is not None
    assert len(units) == 1
    assert units[0][4] == "reg_sh"


def test_multi_no_name_loss():
    """多声明全部名字保留（对齐重组的防丢保护）。"""
    units = _extract_multi("reg [63:0] count_cycle, count_instr;")
    assert units is not None
    names = {u[4] for u in units}
    assert names == {"count_cycle", "count_instr"}


def test_multi_concat_lhs_skipped():
    """声明侧含拼接表达式（`{a, b} = ...`）→ 整行跳过（防逗号吞 token）。"""
    assert _extract_multi("reg [1:0] {a, b} = 2'b11;") is None


def test_multi_comment_skipped():
    assert _extract_multi("// comment") is None


# ── 重组输出：多声明行后续声明符 `, ` 单分隔（P1.5 漂移回归）──

def test_multidecl_recombine_single_space():
    """最小复现（gap 档）：第二声明符落 `, ` 单分隔，不累积填充。"""
    out = _fmt("module m;\n    reg a, b;\n    reg ccc, ddd;\nendmodule\n")
    assert "    reg   a, b;" in out
    assert "    reg   ccc, ddd;" in out
    assert not _DRIFT_RE.search(out)


def test_multidecl_recombine_range_and_idempotent():
    """带位宽多声明：单分隔 + 名字全保留 + 幂等。"""
    src = "module m;\n    reg [7:0] a, b;\n    reg [7:0] cccc, dddd;\nendmodule\n"
    once = _fmt(src)
    assert "    reg  [7:0] a, b;" in once
    assert "    reg  [7:0] cccc, dddd;" in once
    assert not _DRIFT_RE.search(once)
    for name in ("a", "b", "cccc", "dddd"):
        assert re.search(rf"\b{name}\b", once), f"名字丢失: {name}"
    assert _fmt(once) == once  # 幂等（二次格式化不再变）


def test_multidecl_recombine_three_units_with_init():
    """三单元带 init：init 保留、逗号单分隔、名字不丢。"""
    src = "module m;\n    reg a = 1, b = 2, c = 3;\n    reg dd = 4, ee = 5, ff = 6;\nendmodule\n"
    out = _fmt(src)
    assert not _DRIFT_RE.search(out)
    for name in ("a", "b", "c", "dd", "ee", "ff"):
        assert re.search(rf"\b{name}\b", out), f"名字丢失: {name}"


def test_multidecl_port_list_single_space():
    """端口列表多声明（ref 形态 `input C, R, D`）：单分隔。"""
    out = _fmt(
        "module n (\n"
        "    input clk, rst_n,\n"
        "    input C, R, D,\n"
        "    output y\n"
        ");\n"
        "endmodule\n"
    )
    assert "clk, rst_n," in out
    assert "C, R, D," in out
    assert not _DRIFT_RE.search(out)


# ── 正常单声明 ──

def test_simple_reg_no_init():
    cols = _extract("reg [4:0] reg_sh;")
    assert cols is not None
    assert cols[4] == "reg_sh"
    assert cols[1] == "reg"  # first 是声明类型


def test_localparam_integer_kept():
    cols = _extract("localparam integer irq_timer = 0;")
    assert cols is not None
    assert cols[4] == "irq_timer"
    assert cols[2] == "integer"  # opt_type 保留 integer


def test_wire_range():
    cols = _extract("wire [31:0] mem_rdata;")
    assert cols is not None
    assert cols[4] == "mem_rdata"
    assert cols[3] == "[31:0]"


def test_plain_decl():
    cols = _extract("reg irq_delay;")
    assert cols is not None
    assert cols[4] == "irq_delay"


def test_trailing_comma_single_decl_ok():
    # 行尾逗号（端口列表）不算多声明
    cols = _extract("output reg [31:0] mem_addr,")
    assert cols is not None
    assert cols[4] == "mem_addr"


def test_empty_or_comment():
    assert _extract("") is None
    assert _extract("// comment") is None
    assert _extract(";") is None


# ── token 完整性：对齐后不丢 token ──

def test_roundtrip_no_token_loss():
    """extract + join 后，标识符/数字字面量 token 不丢失。"""
    from grammar.verilog.plugins.formatter.passes.column_align import _join_semantic
    lines = [
        "parameter [ 0:0] ENABLE_COUNTERS = 1,",
        "parameter [31:0] LATCHED_IRQ = 32'h ffff_ffff,",
        "parameter [31:0] STACKADDR = 32'h ffff_ffff",
        "reg [4:0] reg_sh;",
        "wire dbg_mem_addr = mem_addr;",
        "localparam integer irq_timer = 0;",
    ]
    for ln in lines:
        cols = _extract(ln)
        if cols is None:
            continue
        out = _join_semantic(cols, [0] * 5)
        # 对齐输出必须保留原行所有标识符（name 不得丢失）
        for word in ln.replace(",", " ").replace(";", " ").split():
            if word[0].isalpha() or word[0] == "_":
                assert word in out, f"{word!r} 在对齐后丢失: {ln!r} -> {out!r}"


def test_is_multidecl():
    assert _is_multidecl(["clk", ",", "resetn", ","])
    assert _is_multidecl(["a", ",", "b", ";"])
    assert not _is_multidecl(["LATCHED_IRQ", "=", "32'h", "ffff_ffff", ","])
    assert not _is_multidecl(["mem_addr", ","])


# ── 注释 token 化（2026-09-17）：注释词不是声明单元 ──

def test_line_comment_is_single_token():
    """行注释整段成一个 token（旧实现按空白切成 `'//', '32-bit', ...`）。"""
    toks = _tokenize_bracket_aware("    reg [31:0] IFPC;   // 32-bit program counter IF state")
    assert toks[-1] == "// 32-bit program counter IF state", toks


def test_block_comment_is_single_token():
    toks = _tokenize_bracket_aware("    reg [7:0] A; /* block comment */")
    assert toks[-1] == "/* block comment */", toks


def test_string_literal_not_split():
    """字符串内的 `//` 不是注释起点，整串成一个 token（本插件无 lexer 对齐）。"""
    toks = _tokenize_bracket_aware('    initial $display("a // b, c");')
    assert '"a // b, c"' in toks, toks


def test_trailing_line_comment_decl_skipped():
    """尾注声明行跳过（保留原文）——旧实现把注释里最后一个标识符当 name，
    重组出 `reg  IFPC // ... [31:0] state`（`;` 落进注释、声明未闭合）。"""
    assert _extract("reg [31:0] IFPC;   // 32-bit program counter IF state") is None
    assert _extract_multi("reg [31:0] IFPC;   // 32-bit program counter IF state") is None


def test_trailing_block_comment_decl_skipped():
    assert _extract("reg [7:0] A; /* block */") is None


def test_align_keeps_trailing_comment_lines_intact():
    """端到端：同组声明行带尾注时，格式化输出保留 `;` 与注释原文（语法不被破坏）。

    回归锚点：曾输出 `reg  IFPC // 32-bit program counter IF [31:0] state`
    ——`;` 被注释吃掉 → sv-parser 判语法错（darkriscv interop）。
    """
    src = (
        "module m;\n"
        "    reg [31:0] IFPC;   // 32-bit program counter IF state\n"
        "    reg [31:0] PC;     // program counter EX stage\n"
        "endmodule\n"
    )
    out = _fmt(src)
    for line in out.split("\n"):
        if "//" in line and line.strip().startswith("reg"):
            head = line.split("//")[0]
            assert ";" in head, f"尾注声明丢 `;`: {line!r}"
    assert "program counter IF state" in out
    assert "program counter EX stage" in out
