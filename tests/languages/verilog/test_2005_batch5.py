"""tests/languages/verilog/test_2005_batch5.py — 2005 全量批次 5（部分）。

覆盖：
    - function 返回类型（A.2.6 function_range_or_type：integer/real/
      realtime/time + signed/range 全形态，ANSI/旧式）
    - task 端口类型（A.2.7 task_port_type：integer/real/realtime/time，
      ANSI/旧式 input/output/inout）
    - generate 单语句体（A.4.2：for/if/else/case 体为单条模块项或空，
      GenBlockOrNull；与过程体 if/case 的候选消歧不冲突）

设计要点（语法文件注释详述）：
    - FuncRangeOrType 分发 FuncRangeSpec（signed/range 可综合返回）与
      FuncScalarType（integer/real/realtime/time，nettypes 关键字）；
      FuncRangeSpec 拆 FuncRangeS/FuncRangeR 两子规则（choice 分支形态
      差异避免 $N 绑定错乱），尾部空格收进子规则（防 `function  f;`）。
    - TaskPortTypeTail 是任务端口的新类型分支（与 TypeSpec 互斥），
      仅任务/函数端口规则引入（模块端口共用规则不动，模块端口类型
      只能是 wire/reg 家族）。
    - GenerateIfDecl/GenerateCaseDecl 挂 InstStmt，候选顺序在过程体
      IfBlock/IfStmt/CaseStmt 之后——过程体内 if/case 仍由原规则消费，
      generate 区域单语句体由此二规则承载；体是 GenBlockOrNull
      （@ModuleItem|@BeginEnd|;）。linter 判别路径与现有候选一致
      （均以 `(` 开头），不干扰 if/case 消歧。
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── function 返回类型（A.2.6）────────────────────────────────


def test_func_ret_scalar_types():
    """function 返回 integer/real/realtime/time（旧式体）。"""
    src = """module m;
    function integer f_int;
        input a;
        f_int = a;
    endfunction
    function real f_real;
        input a;
        f_real = a;
    endfunction
    function realtime f_rt;
        input a;
        f_rt = a;
    endfunction
    function time f_t;
        input a;
        f_t = a;
    endfunction
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in [
        "function integer f_int;",
        "function real f_real;",
        "function realtime f_rt;",
        "function time f_t;",
    ]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_func_ret_signed_range_forms():
    """返回类型 signed/range 各形态保持（含无类型缺省）。"""
    src = """module m;
    function signed f_s;
        input a;
        f_s = a;
    endfunction
    function [7:0] f_r;
        input a;
        f_r = a;
    endfunction
    function signed [15:0] f_sr;
        input a;
        f_sr = a;
    endfunction
    function f_plain;
        input a;
        f_plain = a;
    endfunction
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    for frag in [
        "function signed f_s;",
        "function [7:0] f_r;",
        "function signed [15:0] f_sr;",
        "function f_plain;",
    ]:
        assert frag in out, f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_func_ansi_with_return_type():
    """ANSI 风格带返回类型 + automatic。"""
    src = """module m;
    function automatic integer f (input a, input b);
        f = a + b;
    endfunction
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "function automatic integer f( input a, input b);" in r["output"]
    assert r["idempotent"]


def test_func_old_with_task_port_type():
    """旧式 function 体 input 端口支持 task_port_type。"""
    src = """module m;
    function integer f;
        input integer a;
        f = a;
    endfunction
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "input integer a;" in r["output"]
    assert r["idempotent"]


# ── task 端口类型（A.2.7）────────────────────────────────────


def test_task_old_port_types():
    """旧式 task 体 input/output/inout 支持 task_port_type。"""
    src = """module m;
    task t;
        input integer a;
        output real b;
        inout time c;
        b = a;
    endtask
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # formatter 品类对齐在方向/类型间补列宽空格（`input  integer  a`），
    # 断言按关键字子串匹配。
    for frag in ["input integer a;", "output real b;", "inout time c;"]:
        assert frag.replace(" ", "") in out.replace(" ", ""), f"缺少 {frag!r}:\n{out}"
    assert r["idempotent"]


def test_task_ansi_port_types():
    """ANSI task 端口支持 task_port_type（与 reg 端口混用）。"""
    src = """module m;
    task t (input integer a, output reg b, input real c);
        b = a;
    endtask
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # ANSI 端口在 task 头部括号内，formatter 可能折行 + 品类对齐补空格，
    # 按去全部空格断言。
    flat = out.replace("\n", "").replace(" ", "")
    assert "taskt(" in flat
    assert "inputintegera" in flat
    assert "outputregb" in flat
    assert "inputrealc" in flat
    assert r["idempotent"]


def test_module_port_unchanged():
    """模块端口不引入 task_port_type（模块端口类型只能是 wire/reg 家族）。"""
    src = """module m (input a, output [3:0] y);
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "input a, output [3:0] y" in r["output"]
    assert r["idempotent"]


# ── generate 单语句体（A.4.2）────────────────────────────────


def test_gen_for_single_stmt_body():
    """for generate 单语句体：`for (...) inst;` 无 begin/end。"""
    src = """module m;
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) adder u (a, b);
    endgenerate
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "for (i = 0; i < 4; i = i + 1) adder u (" in r["output"]
    assert r["idempotent"]


def test_gen_for_begin_body_kept():
    """for generate begin/end 体保持（既有形态不回归）。"""
    src = """module m;
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : gen
            adder u (a, b);
        end
    endgenerate
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # BeginEnd 是块规则，head 自带换行（`for (...)` 与 `begin` 分行）——
    # 与改动前 LoopGen 直接 @BeginEnd 的渲染一致（非回归）。
    assert "for (i = 0; i < 4; i = i + 1)" in out
    assert "begin: gen" in out
    assert r["idempotent"]


def test_gen_if_else_single_stmt():
    """if/else generate 单语句体：分支体是单条模块项。"""
    src = """module m;
    parameter P = 1;
    generate
        if (P) adder u (a, b);
        else sub v (a, b);
    endgenerate
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "if (P) adder u (" in out
    assert "else sub v (" in out
    assert r["idempotent"]


def test_gen_case_single_stmt():
    """case generate 单语句体：多项 label + default 空体。"""
    src = """module m;
    parameter W = 8;
    generate
        case (W)
            8, 16: adder u (a, b);
            default: ;
        endcase
    endgenerate
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    assert "8, 16: adder u (" in out
    assert "default: ;" in out
    assert r["idempotent"]


def test_gen_case_begin_body():
    """case generate begin/end 体保持。"""
    src = """module m;
    parameter W = 8;
    generate
        case (W)
            8: begin : g1
                adder u (a, b);
            end
            default: begin : g2
                sub v (a, b);
            end
        endcase
    endgenerate
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # BeginEnd head 渲染 `begin: g1`（无冒号后空格，既有格式）。
    assert "8: begin: g1" in out
    assert r["idempotent"]


def test_procedural_if_case_untouched():
    """过程体 if/case 仍由原规则消费（候选顺序不被 generate 规则抢占）。"""
    src = """module m;
    reg y;
    always @(*) begin
        if (a) y = 1'b1;
        else y = 1'b0;
        case (a)
            1'b0: y = 1'b1;
            default: y = 1'b0;
        endcase
    end
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    out = r["output"]
    # IfStmt 渲染 body 换行缩进（`if (a)` 与 `y = 1'b1;` 分行，既有格式）；
    # 过程体 case 的 `1'b0: y = ...` 单行。
    assert "if (a)" in out and "y = 1'b1;" in out
    assert "1'b0: y = 1'b1;" in out
    assert r["idempotent"]
