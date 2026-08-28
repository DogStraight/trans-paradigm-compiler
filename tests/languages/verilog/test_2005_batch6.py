"""tests/languages/verilog/test_2005_batch6.py — 2005 全量批次 6。

覆盖（覆盖核对确认的 7 个剩余缺口，sv-parser 实现对照见
docs/references.md "2005 覆盖核对 — 7 缺口实现对照"）：
    - 转义标识符（A.9.3 escaped_identifier）：lexer 支持 \\ 起始 id
    - continuous assign strength/delay + 多赋值列表（A.6.1）
    - always 无事件控制（A.6.2：always #5 / always begin）
    - 单索引 range [3]（A.2.5 constant_range_expression）
    - genvar 列表声明（A.4.2 list_of_genvar_identifiers）
    - 实例/门级 attribute 前缀（A.4.1/A.3.1）
    - library 声明 + include 语句（A.1.1 library source text）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── 转义标识符（A.9.3）──────────────────────────────────────


def test_escaped_identifier_lexer():
    """lexer 把 \\ 起始标识符扫描为单个 id（不崩溃、不升级 keyword）。"""
    from lexer import Lexer

    lexer = Lexer(rules_dir="grammar/verilog")
    for src in [r"\my$mod", r"\a.b", r"\always"]:
        toks = lexer.tokenize(src)
        assert len(toks) == 1 and toks[0].type == "id", (
            f"{src!r} 应扫为单个 id，实际 {[t.type for t in toks]}"
        )
        assert toks[0].content == src


def test_escaped_identifier_decl_use():
    """转义名在声明/引用/赋值中端到端可解析且幂等。

    2026-08-28：渲染补空白终止（IEEE A.9.3 转义标识符须以空白止，
    否则转义名后紧跟 ``(`` 会把名字读到括号里去）——断言更新为带终止空格形态。
    """
    src = r"""module \my$mod ;
    wire \a.b ;
    assign \a.b = 1'b0;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert r"module \my$mod ();" in r["output"]
    assert r"wire \a.b ;" in r["output"]
    assert r"assign \a.b  = 1'b0;" in r["output"]
    assert r["idempotent"]


def test_escaped_keyword_name():
    """转义名不受关键字限制（\\always 是合法标识符）。"""
    src = r"""module m;
    wire \always ;
    assign \always = 1'b0;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert r"wire \always ;" in r["output"]
    assert r["idempotent"]


def test_escaped_multi_decl():
    """转义名在逗号列表与表达式引用中。"""
    src = r"""module m;
    wire \a.b, \c.d, \e ;
    assign \a.b = \c.d;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert r"wire \a.b , \c.d , \e ;" in r["output"]
    assert r"assign \a.b  = \c.d ;" in r["output"]
    assert r["idempotent"]


# ── continuous assign strength/delay（A.6.1）─────────────────


def test_assign_strength():
    src = """module m;
    assign (strong1, pull0) y = a & b;
    assign (weak0, weak1) z = a;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign (strong1, pull0) y = a & b;" in r["output"]
    assert "assign (weak0, weak1) z = a;" in r["output"]
    assert r["idempotent"]


def test_assign_delay():
    src = """module m;
    assign #(2, 3) y = a & b;
    assign #5 z = a;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign #(2, 3) y = a & b;" in r["output"]
    assert "assign #5 z = a;" in r["output"]
    assert r["idempotent"]


def test_assign_strength_delay():
    """strength + delay 组合前缀。"""
    src = """module m;
    assign (strong1, pull0) #(1, 2) y = a & b;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign (strong1, pull0) #(1, 2) y = a & b;" in r["output"]
    assert r["idempotent"]


def test_assign_plain_kept():
    """裸 assign 保持（既有形态不回归）。"""
    src = "module m;\n    assign y = a & b;\nendmodule\n"
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign y = a & b;" in r["output"]
    assert r["idempotent"]


# ── always 无事件控制（A.6.2）────────────────────────────────


def test_always_delay_control():
    """always 后直接跟 timing control 语句（always #5 ...）。"""
    src = """module m;
    always #5 clk = ~clk;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "always #5 clk = ~clk;" in r["output"]
    assert r["idempotent"]


def test_always_plain_block():
    """always 后直接跟 begin/end 块（无事件控制）。"""
    src = """module m;
    always begin
        clk = ~clk;
    end
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "always begin" in r["output"]
    assert r["idempotent"]


def test_always_with_event_kept():
    """always @(...) 保持（既有形态不回归）。"""
    src = """module m;
    always @(posedge clk) q <= d;
    always @* y = a & b;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "always @(posedge clk) q <= d;" in r["output"]
    assert "always @* y = a & b;" in r["output"]
    assert r["idempotent"]


# ── 单索引 range（A.2.5）────────────────────────────────────


def test_single_index_range_decl():
    """声明维 [3]（单表达式）与 [7:0]（双表达式）并存。"""
    src = """module m;
    reg [3] a;
    wire [7:0] b;
    reg [WIDTH-1:0] c;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # formatter 品类对齐补列宽空格，按去空白断言
    flat = out.replace("\n", "").replace(" ", "")
    assert "[3]a" in flat
    assert "[7:0]b" in flat
    assert "[WIDTH-1:0]c" in flat
    assert r["idempotent"]


def test_single_index_select():
    """位选择 a[2] 与部分选择 a[1:0]（表达式侧保持）。"""
    src = """module m;
    reg [3:0] a;
    wire b;
    assign b = a[2];
    assign c = a[1:0];
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    flat = out.replace("\n", "").replace(" ", "")
    assert "assignb=a[2];" in flat
    assert "assignc=a[1:0];" in flat
    assert r["idempotent"]


# ── genvar 列表（A.4.2）─────────────────────────────────────


def test_genvar_list():
    """genvar 逗号列表声明 + 单标识符保持。"""
    src = """module m;
    genvar i, j, k;
    genvar s;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    flat = out.replace("\n", "").replace(" ", "")
    assert "genvari,j,k;" in flat
    assert "genvars;" in flat
    assert r["idempotent"]


def test_genvar_list_with_generate():
    """genvar 列表与 generate 循环配合。"""
    src = """module m;
    genvar i, j;
    generate
        for (i = 0; i < 4; i = i + 1) begin : g
            wire w;
        end
    endgenerate
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "genvar i, j;" in r["output"]
    assert r["idempotent"]


# ── 实例/门级 attribute 前缀（A.4.1/A.3.1）──────────────────


def test_attr_on_module_inst():
    """(* ... *) 前缀模块实例。"""
    src = """module m;
    (* keep = 1, dont_touch = 1 *) foo u1 ();
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(* keep = 1, dont_touch = 1 *) foo u1 (" in r["output"]
    assert r["idempotent"]


def test_attr_on_gate():
    """(* ... *) 前缀门级原语。"""
    src = """module m;
    (* keep = 1 *) and g1 (y, a, b);
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(* keep = 1 *) and" in r["output"]
    assert r["idempotent"]


def test_attr_on_decl_kept():
    """声明级 attribute 保持（既有形态不回归）。"""
    src = """module m;
    (* keep = 1 *) reg [3:0] x;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(* keep = 1 *) reg [3:0] x;" in r["output"]
    assert r["idempotent"]


# ── library 声明（A.1.1）────────────────────────────────────


def test_library_declaration():
    """library 声明：单库名 + 多路径 + 与模块共存。"""
    src = """library lib "cells.v", "gates.v";
module top;
    wire a;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert 'library lib "cells.v", "gates.v";' in r["output"]
    assert "module top" in r["output"]
    assert r["idempotent"]


def test_library_incdir():
    """library -incdir 可选段。"""
    src = """library lib "cells.v" -incdir "inc1", "inc2";
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert 'library lib "cells.v" -incdir "inc1", "inc2";' in r["output"]
    assert r["idempotent"]


def test_include_statement():
    """include file_path_spec ;"""
    src = 'include "defs.v";\n'
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert 'include "defs.v";' in r["output"]
    assert r["idempotent"]
