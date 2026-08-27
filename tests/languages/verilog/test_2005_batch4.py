"""tests/languages/verilog/test_2005_batch4.py — 2005 全量批次 4（部分）。

覆盖：
    - specify 块（specify 插件，A.7：specparam/路径声明/系统时序检查）
    - defparam 参数覆盖（A.2.4，与 specify 同批）

设计要点（插件注释详述）：
    - SpecifyDecl 是块规则，specify_item 五类都是 is_statement 规则，
      由块体语句循环自动发现（不逐条 inject）。
    - PathDecl 以 `(` 打头（语句候选 FIRST 集不被可选前缀遮挡）；
      状态依赖路径（if/ifnone 前缀）由 StateDepPathDecl 包裹。
    - PathToken 宽松覆盖路径描述（=>/*>/posedge/negedge/+/-/+/:-:/区间/
      括号组）；裸括号不作 token，嵌套组由 PathParenGroup 递归消费。
    - TimingCheckDecl 用 TimingCheckArg 列表（timing_check_event 或
      表达式），$setup(a, posedge clk, 1) 的事件参数可解析。
    - PathDelayValue 拆 PathDelayList/PathDelayParen 两形态
      （(1, 2) 括号延迟）。
    - defparam 值复用 PathDelayAtom（constant_mintypmax，a 或 a:b:c），
      层级名 top.u1.WIDTH 由 HierId 覆盖。
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── specify 块 ────────────────────────────────────────────────


SPECIFY_SRC = """module m;
    input a, b, clk, d, reset;
    output y, q;
    specify
        specparam tRise = 1, tFall = 2;
        pulsestyle_onevent a, b;
        showcancelled y;
        (a => y) = (1, 2);
        (a, b *> y) = 3;
        (posedge clk => (q +: d)) = (1, 2, 3);
        if (reset) (a => y) = (1, 2);
        ifnone (a => y) = 3;
        $setup(a, posedge clk, 1);
        $hold(posedge clk, a, 1, notifier);
        $width(posedge clk, 10);
        $period(posedge clk, 20);
        $setuphold(posedge clk, d, 1, 2, notifier);
        $width(edge [01, x1] clk, 10);
        $setup(posedge clk &&& reset, d, 1);
    endspecify
endmodule
"""


def test_specify_block_roundtrip():
    """specify 块全形态：specparam/路径/时序检查，渲染保真 + 幂等。"""
    r = _run(SPECIFY_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in [
        "specify",
        "endspecify",
        "specparam tRise = 1, tFall = 2;",
        "pulsestyle_onevent a, b;",
        "showcancelled y;",
        "(a => y) = (1, 2);",
        "(posedge clk => (q +: d)) = (1, 2, 3);",
        "if (reset) (a => y) = (1, 2);",
        "ifnone (a => y) = 3;",
        "$setup(a, posedge clk, 1);",
        "$hold(posedge clk, a, 1, notifier);",
        "$width(posedge clk, 10);",
        "$setuphold(posedge clk, d, 1, 2, notifier);",
        "$setup(posedge clk &&& reset, d, 1);",
    ]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_specparam_mintypmax_and_range():
    """specparam 值支持 mintypmax（1:2:3）与范围前缀（[7:0]）。"""
    src = """module m;
    specify
        specparam t = 1:2:3;
        specparam [7:0] width = 8;
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "specparam t = 1 : 2 : 3;" in out
    assert "specparam [7:0] width = 8;" in out
    assert r["idempotent"]


def test_path_decl_full_and_edge():
    """全路径（*> 多输入输出）与边沿敏感路径（posedge/negedge 前缀）。"""
    src = """module m;
    input a, b, clk, d;
    output y, z;
    specify
        (a, b *> y, z) = 3;
        (posedge clk => (q +: d)) = 1;
        (negedge clk => (q -: d)) = 1;
        (a + => y) = 1;
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in ["(a , b *> y , z) = 3;", "(posedge clk => (q +: d)) = 1;",
                 "(negedge clk => (q -: d)) = 1;", "(a + => y) = 1;"]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_state_dependent_path_renders_prefix():
    """if/ifnone 前缀保留（渲染不含前缀丢失）。"""
    src = """module m;
    input a, y, reset;
    specify
        if (reset) (a => y) = 1;
        ifnone (a => y) = 2;
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "if (reset) (a => y) = 1;" in out
    assert "ifnone (a => y) = 2;" in out
    assert r["idempotent"]


def test_timing_check_event_forms():
    """时序检查的事件参数：edge 控制、&&& 条件、多参数形态。"""
    src = """module m;
    input clk, d, reset;
    specify
        $recovery(posedge reset, d, 1);
        $nochange(posedge clk, d, 0, 0);
        $skew(posedge clk, negedge clk, 1);
        $timeskew(edge [01, x1] clk, d, 1);
        $fullskew(posedge clk, d, 1, 2, notifier);
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in [
        "$recovery(posedge reset, d, 1);",
        "$nochange(posedge clk, d, 0, 0);",
        "$skew(posedge clk, negedge clk, 1);",
        "$timeskew(edge [01,x1] clk, d, 1);",
        "$fullskew(posedge clk, d, 1, 2, notifier);",
    ]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_path_delay_value_forms():
    """路径延迟：单值/双值/三值/括号形态/超长形态不折行。"""
    src = """module m;
    input a, y;
    specify
        (a => y) = 1;
        (a => y) = (1, 2);
        (a => y) = (1, 2, 3);
        (a => y) = (1, 2, 3, 4, 5, 6);
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in ["(a => y) = 1;", "(a => y) = (1, 2);",
                 "(a => y) = (1, 2, 3);", "(a => y) = (1, 2, 3, 4, 5, 6);"]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_path_decl_long_stays_single_line():
    """路径描述符是语法原子：超 40 列不逐 token 折行（no_soft）。"""
    src = """module m;
    input clk, d;
    output q;
    specify
        (posedge clk => (q +: d)) = (1, 2, 3);
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(posedge clk => (q +: d)) = (1, 2, 3);" in r["output"]
    assert r["idempotent"]


def test_pulsestyle_showcancelled_variants():
    """pulsestyle_ondetect / noshowcancelled 变体。"""
    src = """module m;
    input a, b, c;
    specify
        pulsestyle_ondetect a, b, c;
        noshowcancelled a;
    endspecify
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "pulsestyle_ondetect a, b, c;" in out
    assert "noshowcancelled a;" in out
    assert r["idempotent"]


# ── defparam（A.2.4）──────────────────────────────────────────


def test_defparam_roundtrip():
    """defparam 层级参数覆盖：层级名 + 普通值 + mintypmax 值。"""
    src = """module top;
    defparam u1.WIDTH = 8, u2.DEPTH = 16;
    sub u1 ();
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "defparam u1.WIDTH = 8, u2.DEPTH = 16;" in out
    assert r["idempotent"]


def test_defparam_mintypmax_value():
    src = """module top;
    defparam u1.DELAY = 1:2:3;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "defparam u1.DELAY = 1 : 2 : 3;" in r["output"]
    assert r["idempotent"]


def test_defparam_module_level_only():
    """defparam 是模块级声明：不在过程体内解析（sim 无关）。"""
    src = "module m;\n    defparam u1.W = 4;\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "defparam u1.W = 4;" in r["output"]
    assert r["idempotent"]
