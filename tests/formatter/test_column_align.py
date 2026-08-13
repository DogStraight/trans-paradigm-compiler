"""column_align 语义列提取——数据破坏回归测试。

保护重点：
  1. 带空格数字字面量 init（`32'h ffff_ffff`）不得把 `ffff_ffff` 误判为 name 而丢真名
  2. 一行多声明/多端口（`input clk, resetn,` / `reg a, b;`）不得丢名字（跳过保留原文）
"""

from grammar.verilog.plugins.formatter.passes.column_align import (
    _tokenize_bracket_aware,
    _extract_semantic,
    _is_multidecl,
)


def _extract(line: str):
    """行文本 → 语义列。"""
    toks = _tokenize_bracket_aware(line)
    return _extract_semantic(toks)


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
