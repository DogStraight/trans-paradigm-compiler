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


# ── 跨行端口（concat 多行展开）──

UNCLOSED_PORT_LINES = [
    "        SB_RAM40_4K inst (",
    "        .RE(pd(RE)),",
    "        .RADDR({pd(RADDR_10),",
    "            pd(RADDR_9),",
    "            pd(RADDR_0)}),",
    "        .WCLK(pd(WCLK) ^ NEG_CLK_W)",
    "        );",
]


def test_unclosed_port_skipped_without_parser():
    """无 parser：跨行端口首行不参与对齐、不被伪补 `)`（2026-08-28 缺陷 4 回归）。

    保守语义：未闭合行打断连续端口组（跨组不对齐），但整行原文保留——无损坏。
    """
    out = run_inst_port_align(list(UNCLOSED_PORT_LINES), [])
    # 未闭合行保持原文（不补 `)`、不拆）
    assert out[2] == "        .RADDR({pd(RADDR_10),"
    # 组被未闭合行打断：其余端口行保持原样（保守，无损坏）
    assert out[1] == "        .RE(pd(RE)),"
    assert out[5] == "        .WCLK(pd(WCLK) ^ NEG_CLK_W)"
    # 续行不变
    assert out[3] == "            pd(RADDR_9),"
    assert out[4] == "            pd(RADDR_0)}),"


def _make_parser():
    """构建带 lexer 的 parser（AST 辅助注入用）。"""
    import os

    from core.config_registry import ConfigRegistry
    from core.define import (
        GrammarRulesRegister,
        DEFAULT_RULES_DIR,
        DEFAULT_EXT_DIRS,
    )
    from lexer import Lexer
    from parser import Parser, setup_grammar
    from parser.rule_selector import RuleSelector

    ConfigRegistry.load_all(
        DEFAULT_RULES_DIR,
        ext_dirs=DEFAULT_EXT_DIRS,
        plugins_dir=os.path.join(DEFAULT_RULES_DIR, "plugins"),
    )
    rules = setup_grammar(
        DEFAULT_RULES_DIR,
        GrammarRulesRegister.get_default(),
        ext_dirs=DEFAULT_EXT_DIRS,
    )
    lexer = Lexer(rules_dir=DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)
    sel = RuleSelector(
        rules,
        [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ],
    )
    parser = Parser(rules_dir=DEFAULT_RULES_DIR, rules=rules, rule_selector=sel)
    parser.lexer = lexer
    return parser


def test_unclosed_port_aligned_with_parser():
    """AST 辅助：跨行端口参与 name 列对齐，expr 原文保留（ice40 形态）。"""
    parser = _make_parser()
    out = run_inst_port_align(list(UNCLOSED_PORT_LINES), [], parser=parser)
    # 跨行端口首行：name 列与 .RE/.WCLK 对齐（.WCLK 最长），expr 原样
    assert out[2] == "        .RADDR({pd(RADDR_10),"
    # 单行端口全对齐（name + expr 两列）
    assert out[1] == "        .RE   (pd(RE)              ),"
    assert out[5] == "        .WCLK (pd(WCLK) ^ NEG_CLK_W)"
    # 续行不变
    assert out[3] == "            pd(RADDR_9),"
    assert out[4] == "            pd(RADDR_0)}),"
