"""tests/languages/verilog/test_2005_batch3.py — 2005 全量批次 3（部分）。

覆盖：
    - 门级/开关原语实例化（gates 插件，A.3：26 原语 + strength/delay）
    - 模块实例位置端口连接（A.4.1.1 ordered port connection——UDP 实例依赖）
    - UDP 声明（udp 插件，A.5：comb/seq 表 + initial + edge 括号对）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── 门级原语 ────────────────────────────────────────────────


GATE_SRC = """module m;
    wire a, b, y, o1, o2, en, ctl;
    and g1 (y, a, b);
    or (o1, a, b, ctl);
    nand #5 n1 (o2, a, b);
    not (strong0, pull1) n2 (y, a);
    bufif1 (y, a, en);
    nmos n3 (y, a, ctl);
    cmos c1 (y, a, ctl, ~ctl);
    tran t1 (a, b);
    pullup (strong1) p1 (y);
    pulldown (weak0) p2 (y);
    and #(1, 2) g2 [3:0] (y, a, b);
endmodule
"""


def test_gate_instantiation_roundtrip():
    """门级实例全形态：有名/无名实例、strength、delay、数组实例。

    formatter 品类对齐会在 gate 类型与实例名间插对齐空格（and  g1(...)），
    断言按子串匹配（实例名 + 括号连接形态），不断言精确列宽。
    """
    r = _run(GATE_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in [
        "g1(y, a, b);",
        "or (o1, a, b, ctl);",
        "n1(o2, a, b);",
        "(strong0, pull1)",
        "n2(y, a);",
        "bufif1 (y, a, en);",
        "n3(y, a, ctl);",
        "c1(y, a, ctl, ~ctl);",
        "t1(a, b);",
        "(strong1)",
        "p1(y);",
        "(weak0)",
        "p2(y);",
        "#(1, 2)",
        "g2[3:0](y, a, b);",
    ]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_all_gate_types_keywords():
    """26 原语关键字全集可解析。"""
    gates = [
        "and", "nand", "or", "nor", "xor", "xnor",
        "buf", "not", "bufif0", "bufif1", "notif0", "notif1",
        "nmos", "pmos", "rnmos", "rpmos", "cmos", "rcmos",
        "tran", "tranif0", "tranif1", "rtran", "rtranif0", "rtranif1",
        "pullup", "pulldown",
    ]
    body = "\n".join(f"    {g} g{i} (y, a);" for i, g in enumerate(gates))
    src = f"module m;\n    wire y, a;\n{body}\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert r["idempotent"]


# ── 模块实例位置连接 ────────────────────────────────────────


def test_ordered_port_connection():
    """位置端口连接（A.4.1.1）：模块实例 + UDP 实例共用。"""
    src = (
        "module m;\n"
        "    wire a, b, y;\n"
        "    my_and u1 (y, a, b);\n"
        "endmodule\n"
        "\n"
        "module my_and(out, in1, in2);\n"
        "    input in1, in2;\n"
        "    output out;\n"
        "    assign out = in1 & in2;\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # ModuleInst 端口渲染为 body 多行形态（命名连接同款）：
    #   my_and u1 (
    #       y, a, b
    #       );
    assert "u1 (" in out
    assert "y, a, b" in out
    assert r["idempotent"]


# ── UDP 声明 ────────────────────────────────────────────────


UDP_COMB_SRC = """primitive mux2 (out, sel, a, b);
    output out;
    input sel, a, b;
    table
        0 0 ? : 0;
        0 1 ? : 1;
        1 ? 0 : 0;
        1 ? 1 : 1;
        x ? 0 0 : x;
    endtable
endprimitive
"""

UDP_SEQ_SRC = """primitive dff (q, clk, d);
    output reg q;
    input clk, d;
    initial q = 1'b0;
    table
        (01) 0 : ? : 0;
        (01) 1 : ? : 1;
        ? ? : ? : -;
    endtable
endprimitive
"""


def test_udp_combinational_roundtrip():
    r = _run(UDP_COMB_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for line in [
        "primitive mux2(out, sel, a, b);",
        "table",
        "0 0 ? : 0;",
        "x ? 0 0 : x;",
        "endtable",
        "endprimitive",
    ]:
        assert line in out, f"缺少 {line!r}:\n{out}"
    assert r["idempotent"]


def test_udp_sequential_roundtrip():
    r = _run(UDP_SEQ_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "initial q = 1'b0;" in out
    assert "(01) 0 : ? : 0;" in out
    assert "? ? : ? : -;" in out
    assert "endprimitive" in out
    assert r["idempotent"]


def test_udp_two_blocks_flat_roundtrip():
    """同文件两个 UDP 块：AST 平级（Root 下两个 UdpDecl），非嵌套。"""
    r = _run(UDP_COMB_SRC + "\n" + UDP_SEQ_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "primitive mux2(out, sel, a, b);" in out
    assert "primitive dff(q, clk, d);" in out
    names = [getattr(c, "node_name", None) for c in (r["ast"].sub_node or [])]
    assert names == ["UdpDecl", "UdpDecl"], names
    assert r["idempotent"]


def test_udp_instance_via_module_inst():
    """UDP 实例化复用 ModuleInst（位置连接）。"""
    src = UDP_COMB_SRC + "\nmodule m;\n    wire s, a, b, y;\n    mux2 u1 (y, s, a, b);\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "u1 (" in out
    assert "y, s, a, b" in out
