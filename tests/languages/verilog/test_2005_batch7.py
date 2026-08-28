"""tests/languages/verilog/test_2005_batch7.py — 真实语料驱动的 2005 补全。

真实语料实测（tests/e2e/samples/real/ref/，见 test_real_corpus.py）暴露的
4 个缺口，本次落地：
    - `===` / `!==`（A.8.4 case_equality/case_inequality）：token +
      CmpOp + operator 表三处缺失（ice40 cells_sim 大量使用）
    - 多目标连续赋值（A.6.1 list_of_net_assignments）：`assign a = b, c = d;`
      （ice40 ~17 处 / yosys techmap 实证；批次 6 曾因 linter 误判延后，
      现以独立 AssignExtra 子规则落地）
    - 模块头属性（A.1.1 module_declaration 前缀 attribute_instance）：
      `(* keep *) module m (...)`（ice40 13 个模块）
    - 语句体宏行尾补分号（preprocessor/_expand.py）：非空 body 宏独占一行
      无分号时展开为 `tpc_marker_N;`（按 A.6.9 task_enable 裸任务调用可解析），
      此前裸 `id` 不是合法语句，lint/parser 双拒（ice40 `SB_DFF_INIT 等）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── `===` / `!==`（A.8.4 case_equality / case_inequality）────────────────


def test_case_equality_lexer():
    """`===`/`!==` 扫描为单个 extend 符号 token。"""
    from lexer import Lexer

    lexer = Lexer(rules_dir="grammar/verilog")
    toks = lexer.tokenize("a === b !== c")
    types = [t.type for t in toks]
    assert "symbol.extend.case_equal" in types
    assert "symbol.extend.case_not_equal" in types


def test_case_equality_wire_decl():
    """`===` 在 wire 声明/assign/过程体中端到端可解析且幂等。"""
    src = """module m;
    wire w = a === 1'bz;
    assign x = (a !== 1'bz) ? 1'b0 : a;
    always @* begin
        y = (a === 1'bz) ? 1'b1 : 1'b0;
    end
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "wire w = a === 1'bz;" in r["output"]
    assert "assign x = (a !== 1'bz) ? 1'b0 : a;" in r["output"]
    assert "y = (a === 1'bz) ? 1'b1 : 1'b0;" in r["output"]
    assert r["idempotent"]


def test_case_equality_in_function():
    """`===` 在 function 体（pd/pu 拉电阻风格，ice40 实证）。"""
    src = """module m;
    function pd;
        input x;
        begin
            pd = (x === 1'bz) ? 1'b0 : x;
        end
    endfunction
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "pd = (x === 1'bz) ? 1'b0 : x;" in r["output"]
    assert r["idempotent"]


def test_case_equality_precedence():
    """`===` 与 `==` 同级：`a === b == c` 与 `a == b === c` 均可解析。"""
    for expr in ("a === b == c", "a == b === c", "a !== b != c"):
        r = _run(f"module m; wire w = {expr}; endmodule\n")
        assert r["success"], f"{expr}: {r.get('error', '')}"
        assert r["idempotent"]


def test_case_inequality_survives_column_align():
    """formatter 列对齐不拆 `!==`/`!=`（2026-08-28 审查发现：对齐前被拆成
    `d ! == e`，重组后运算符语义破坏；column_align 已并入前导 `!`）。"""
    src = """module m;
    wire a = b !== c;
    wire long_name = d !== e;
    wire x = f != g;
    wire y = h === i;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    # 列对齐后 wire 与名字间空格可变（对齐填充），运算符本体断言用去空白比较
    flat = "".join(r["output"].split())
    for expect in ("wirea=b!==c;", "wirelong_name=d!==e;", "wirex=f!=g;", "wirey=h===i;"):
        assert expect in flat, f"缺少 {expect!r}，输出: {r['output']}"
    assert "! == " not in r["output"]
    assert r["idempotent"]


# ── 多目标连续赋值（A.6.1 list_of_net_assignments）─────────────────────


def test_assign_multi_target():
    """`assign a = b, c = d;` 多目标列表解析 + 渲染 + 幂等。"""
    src = """module m;
    assign a = b, c = d;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign a = b, c = d;" in r["output"]
    assert r["idempotent"]


def test_assign_multi_three_targets():
    """三目标与 strength/delay 前缀组合（ice40 实证形态）。"""
    src = """module m;
    assign (strong1, pull0) y = a, z = b, w = c;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign (strong1, pull0) y = a, z = b, w = c;" in r["output"]
    assert r["idempotent"]


def test_assign_multi_single_regression():
    """单目标 assign 不受影响（含 strength/delay 前缀）。"""
    src = """module m;
    assign a = b;
    assign #(1, 2) c = d;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "assign a = b;" in r["output"]
    assert "assign #(1, 2) c = d;" in r["output"]
    assert r["idempotent"]


# ── 模块头属性（A.1.1 attribute_instance 前缀 module_declaration）───────


def test_module_attribute():
    """`(* keep *) module` 模块头属性（ice40 `(* abc9_* *)` 实证）。"""
    src = """(* keep *)
module m;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(* keep *)" in r["output"]
    assert r["idempotent"]


def test_module_attribute_with_ports_and_multi_specs():
    """多属性项 + 端口列表 + 值属性。"""
    src = """(* abc9_flop, lib_whitebox = 1 *)
module m (input a, output y);
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(* abc9_flop, lib_whitebox = 1 *)" in r["output"]
    assert "module m( input a, output y);" in r["output"]
    assert r["idempotent"]


def test_module_attribute_macromodule():
    """模块头属性同样适用于 macromodule 变体。"""
    src = """(* keep *)
macromodule m;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "(* keep *)" in r["output"]
    assert r["idempotent"]


def test_module_attribute_no_attr_still_works():
    """无属性模块不受影响。"""
    r = _run("module m; endmodule\n")
    assert r["success"]
    assert "module m();" in r["output"]


# ── 语句体宏行尾补分号（preprocessor/_expand.py）────────────────────────


def test_statement_body_macro_line_final():
    """非空 body 宏独占一行无分号 → 展开 `tpc_marker_N;` 可解析并还原。

    ice40 实证：`define SB_DFF_INIT initial Q = 0;` 在模块体独占一行使用。
    此前展开为裸 `tpc_marker_N`（裸 id 非合法语句），lint/parser 双拒。
    """
    src = """module m;
`define BODY initial q = 1;
`BODY
always @* q = 1;
endmodule
"""
    r = _run(src, expand_macros=True)
    assert r["success"], r.get("error", "")
    assert "`BODY" in r["output"]  # 还原为宏调用
    assert "tpc_marker" not in r["output"]


def test_statement_body_macro_with_semicolon():
    """调用后已有分号不受影响（picorv32 `assert 式）。"""
    src = """module m;
`define BODY2 q = 1;
`BODY2;
endmodule
"""
    r = _run(src, expand_macros=True)
    assert r["success"], r.get("error", "")
    assert "`BODY2;" in r["output"]
    assert "tpc_marker" not in r["output"]


def test_expression_macro_mid_line_unchanged():
    """表达式位宏（行尾有内容）不补分号，行为不变。"""
    src = """module m;
`define W 8
wire [(`W)-1:0] a;
endmodule
"""
    r = _run(src, expand_macros=True)
    assert r["success"], r.get("error", "")
    assert "`W" in r["output"]
    assert "tpc_marker" not in r["output"]
