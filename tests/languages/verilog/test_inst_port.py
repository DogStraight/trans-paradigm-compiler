"""inst_port.py 实例端口对齐测试。

能力：
  1. 拆单行多端口（括号平衡）
  2. 连续端口行对齐 name / expr 两列
  3. 括号嵌套 expr 正确解析
"""

from grammar.verilog.plugins.formatter.passes.inst_port import (
    run_inst_port_align,
    _split_line_ports,
    _match_port,
)


# ── 单行多端口拆分 ──

def test_split_multi_ports():
    line = "            .clk(clk), .resetn(resetn), .pcpi_valid(pcpi_valid);"
    segs = _split_line_ports(line)
    assert segs is not None
    assert len(segs) == 3
    assert segs[0] == "            .clk(clk),"
    assert segs[1] == "            .resetn(resetn),"
    assert segs[2] == "            .pcpi_valid(pcpi_valid);"


def test_split_single_port_not_split():
    assert _split_line_ports("    .clk(clk),") is None
    assert _split_line_ports("module m;") is None


def test_split_nested_parens():
    # .port($signed(x)) 的括号嵌套
    line = "    .a($signed(x)), .b({c, d});"
    segs = _split_line_ports(line)
    assert segs is not None
    assert segs[0] == "    .a($signed(x)),"
    assert segs[1] == "    .b({c, d});"


def test_split_no_trailing_comma():
    line = "    .a(1), .b(2)"
    segs = _split_line_ports(line)
    assert segs is not None
    assert segs[0] == "    .a(1),"
    assert segs[1] == "    .b(2)"


# ── 端口解析 ──

def test_match_port_basic():
    m = _match_port("    .clk(clk),")
    assert m is not None
    indent, name, expr, term = m
    assert indent == "    "
    assert name == ".clk"
    assert expr == "clk"
    assert term == ","


def test_match_port_nested():
    m = _match_port("        .pcpi_rd (pcpi_int_rd),")
    assert m is not None
    assert m[1] == ".pcpi_rd"
    assert m[2] == "pcpi_int_rd"
    assert m[3] == ","


def test_match_port_empty():
    m = _match_port("    .foo(),")
    assert m is not None
    assert m[2] == ""


def test_match_port_not_port():
    assert _match_port("    assign x = 1;") is None
    assert _match_port("module m;") is None


# ── 对齐 ──

def test_align_aligned_columns():
    lines = [
        "    .clk(clk),",
        "    .resetn(resetn),",
        "    .pcpi_valid(pcpi_valid)",
    ]
    out = run_inst_port_align(lines, [])
    # name 列宽 11（.pcpi_valid），expr 列宽 10（pcpi_valid）
    assert out[0] == "    .clk       (clk       ),"
    assert out[1] == "    .resetn    (resetn    ),"
    assert out[2] == "    .pcpi_valid(pcpi_valid)"


def test_align_split_multi_ports():
    # 单行多端口 → 拆分 + 对齐
    lines = [
        "            u0 (",
        "            .clk(clk), .resetn(resetn), .data(data)",
        "            );",
    ]
    out = run_inst_port_align(lines, [])
    # 端口行被拆成 3 行并对齐
    port_lines = [l for l in out if l.strip().startswith(".")]
    assert len(port_lines) == 3
    assert port_lines[0].strip().startswith(".clk")
    assert port_lines[1].strip().startswith(".resetn")
    assert port_lines[2].strip().startswith(".data")


def test_token_preserved():
    """对齐只改空白，端口 token 不丢。"""
    lines = [
        "    .clk(clk), .resetn(resetn), .pcpi_valid(pcpi_valid)",
    ]
    out = run_inst_port_align(lines, [])
    joined = "".join(out)
    for tok in (".clk", "clk", ".resetn", "resetn", ".pcpi_valid", "pcpi_valid"):
        assert tok in joined
