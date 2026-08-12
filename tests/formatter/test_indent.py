"""indent.py 缩进重排 pass 测试。

规则：块头行（module/begin/case 等）缩进到 depth-1（与配对 end 对齐），
其余行按 depth 缩进；只改行首空白，token 不丢。
"""

from grammar.verilog.plugins.formatter.boundary import LineContext, ScopeKind
from grammar.verilog.plugins.formatter.passes.indent import run_indent_pass


def _ctx(depth: int, hdr=None, ftr=None, text: str = "") -> LineContext:
    return LineContext(
        line_number=1,
        text=text,
        scope_depth=depth,
        block_header_of=hdr,
        block_footer_of=ftr,
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
