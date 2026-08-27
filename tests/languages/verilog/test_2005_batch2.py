"""tests/languages/verilog/test_2005_batch2.py — 2005 全量批次 2。

覆盖：
    - procedural assign/deassign（sim 插件，A.6.4 procedural_continuous_assignments）
    - config 声明（configs 插件，A.1.5：design/default/instance/cell/liblist/use）
    - macromodule（主包，A.1.2 module_keyword 变体）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── procedural assign / deassign ──────────────────────────────


def test_proc_assign_deassign_roundtrip():
    """过程连续赋值 + 解除：与模块级 assign 并存不混淆。"""
    src = (
        "module m;\n"
        "    reg a, b;\n"
        "    wire w1;\n"
        "    assign w1 = a;\n"
        "    always @(*) begin\n"
        "        assign a = b;\n"
        "        deassign a;\n"
        "        force a = 1'b1;\n"
        "        release a;\n"
        "    end\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "assign w1 = a;" in out
    assert "assign a = b;" in out
    assert "deassign a;" in out
    assert "force a = 1'b1;" in out
    assert "release a;" in out
    assert r["idempotent"]


def test_deassign_lvalue_forms():
    """deassign 的 lvalue 形态：位选/部分选（PrimaryExpr 覆盖）。"""
    src = (
        "module m;\n"
        "    reg [7:0] v;\n"
        "    always @(*) begin\n"
        "        assign v[3:0] = 4'b0000;\n"
        "        deassign v[3:0];\n"
        "    end\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "deassign v[3:0];" in r["output"]
    assert r["idempotent"]


# ── config 声明 ──────────────────────────────────────────────


CONFIG_SRC = """config cfg1;
    design rtlLib.top, gateLib.top;
    default liblist rtlLib;
    instance top.a1 liblist gateLib;
    instance top.a2 use rtlLib.counter:config;
    cell rtlLib.adder liblist rtlLib gateLib;
    cell gateLib.dff use rtlLib.dff;
endconfig

module m;
endmodule
"""


def test_config_decl_roundtrip():
    """config 块全形态：design/default/instance/cell/liblist/use。"""
    r = _run(CONFIG_SRC)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for line in [
        "config cfg1;",
        "design rtlLib.top, gateLib.top;",
        "default liblist rtlLib;",
        "instance top.a1 liblist gateLib;",
        "instance top.a2 use rtlLib.counter:config;",
        "cell rtlLib.adder liblist rtlLib gateLib;",
        "cell gateLib.dff use rtlLib.dff;",
        "endconfig",
    ]:
        assert line in out, f"缺少 {line!r}:\n{out}"
    assert r["idempotent"]


def test_config_minimal():
    """最小 config 块（仅 design 语句）。"""
    src = "config c1;\n    design lib.top;\nendconfig\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "design lib.top;" in r["output"]
    assert r["idempotent"]


def test_config_missing_design_linted():
    """缺 design 语句的 config 块：linter 块级检查报错（不静默）。"""
    from linter.scanner import LinterScanner

    sc = LinterScanner(rules_dir="grammar/verilog", ext_dirs=["grammar/verilog/plugins"])
    diags = sc.scan("config c1;\n    default liblist a;\nendconfig\n")
    assert diags, "缺 design 语句应有诊断"


# ── macromodule ──────────────────────────────────────────────


def test_macromodule_roundtrip():
    """macromodule 声明：块起止配对 + 渲染保真。"""
    src = (
        "macromodule mm(\n"
        "    input clk,\n"
        "    output reg q\n"
        ");\n"
        "    always @(posedge clk) begin\n"
        "        q <= 1'b1;\n"
        "    end\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "macromodule mm" in r["output"]
    assert r["idempotent"]
