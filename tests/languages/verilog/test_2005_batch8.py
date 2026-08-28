"""tests/languages/verilog/test_2005_batch8.py — A 类缺口修复。

2026-08-28 缺口修复批次（实测确认的 3 个语法缺口）：
    - 层次化 id 表达式位（A.9.3 hierarchical_identifier）：`a.b` / `a.b.c` /
      `a.b[3:0]` 在表达式/赋值位解析（HierExpr 原子，与 SelectExpr a[0]、
      纯 Identifier 共存；真实代码高频——assign x = top.u1.q）
    - 无括号系统任务语句（A.6.2/A.9 sys_task_enable）：`$finish;` / `$stop;`
      括号整体可选（SysTaskStmt），`$display(...)` 带参形态不受影响
    - 参数覆盖 mintypmax（A.4.3 参数值 / A.8.2 mintypmax_expression）：
      `#(.P(1:2:3))` 命名参数值位改用 MintypmaxExpr（单值天然兼容）
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


# ── A1 层次化 id 表达式位（A.9.3 hierarchical_identifier）────────────────


def test_hier_ident_basic():
    """`a.b` 在 wire 声明/assign 中解析 + 渲染保真 + 幂等。"""
    src = """module m;
    wire w = a.b;
    assign x = top.u1.q;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "wire w = a.b;" in r["output"]
    assert "assign x = top.u1.q;" in r["output"]
    assert r["idempotent"]


def test_hier_ident_multi_member_and_suffix():
    """多级成员 + 下标后缀：a.b.c / a.b[3:0]（下标在成员链之后，标准形态）。"""
    src = """module m;
    wire w = a.b.c;
    wire x = a.b[3:0];
    wire y = p.q.r[0][1];
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    flat = "".join(r["output"].split())
    for expect in ("wirew=a.b.c;", "wirex=a.b[3:0];", "wirey=p.q.r[0][1];"):
        assert expect in flat, f"缺少 {expect!r}: {r['output']}"
    assert r["idempotent"]


def test_hier_ident_in_expression_ops():
    """层级引用参与比较/逻辑运算（与 CmpOp 等组合）。"""
    src = """module m;
    wire w = a.b == c.d;
    always @* y = x.a && b.c;
    assign z = top.u.q[0] | r.s;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    flat = "".join(r["output"].split())
    for expect in ("wirew=a.b==c.d;", "y=x.a&&b.c;", "assignz=top.u.q[0]|r.s;"):
        assert expect in flat, f"缺少 {expect!r}: {r['output']}"
    assert r["idempotent"]


def test_hier_ident_plain_forms_unchanged():
    """纯标识符/纯下标不受影响（SelectExpr/Identifier 回归）。"""
    src = """module m;
    wire a = b;
    wire c = d[0];
    wire e = f[3:0];
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    flat = "".join(r["output"].split())
    for expect in ("wirea=b;", "wirec=d[0];", "wiree=f[3:0];"):
        assert expect in flat, f"缺少 {expect!r}: {r['output']}"
    assert r["idempotent"]


def test_hier_ident_typed_ports_coexist():
    """typed_ports 点语法（端口列表类型引用 spi.slave）不受影响——表达式位
    新增 `.` 能力不能破坏声明/端口位的既有解析。"""
    src = """module top (
    spi.slave spi_io
);
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "spi.slave" in r["output"]


# ── A2 无括号系统任务语句（A.6.2/A.9 sys_task_enable）───────────────────


def test_sys_task_no_parens():
    """`$finish;` / `$stop;` 无括号形态（真实 testbench 高频）。"""
    src = """module m;
    initial $finish;
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "initial $finish;" in r["output"]
    assert r["idempotent"]


def test_sys_task_no_parens_in_block_and_if():
    """无括号形态在 begin 块/if 体/always 中。"""
    src = """module m;
    always @* if (a) $stop;
    initial begin
        $finish;
    end
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    flat = "".join(r["output"].split())
    assert "if(a)$stop;" in flat, f"if 体 $stop 丢失: {r['output']}"
    assert "$finish;" in r["output"]
    assert r["idempotent"]


def test_sys_task_with_args_unchanged():
    """带括号系统任务不受影响（$display/$readmemh 参数完整）。"""
    src = """module m;
    initial begin
        $display("hello");
        $display("x=%d", a);
        $readmemh("f.txt", mem);
    end
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert '$display("hello");' in r["output"]
    assert '$display("x=%d", a);' in r["output"]
    assert '$readmemh("f.txt", mem);' in r["output"]
    assert r["idempotent"]


# ── A3 参数覆盖 mintypmax（A.4.3/A.8.2）─────────────────────────────────


def test_param_override_mintypmax():
    """`#(.P(1:2:3))` 命名参数 mintypmax 形态。"""
    src = """module m;
    u #(.P(1:2:3)) u1 ();
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "#(.P(1 : 2 : 3))" in r["output"]
    assert r["idempotent"]


def test_param_override_mintypmax_mixed():
    """mintypmax 与单值混合、与位置参数并存。"""
    src = """module m;
    u #(.P(1:2:3), .Q(4)) u1 ();
    v #(.WIDTH(8), .DEPTH(16)) v1 ();
    w #(Mode, IOWait) w1 ();
endmodule
"""
    r = _run(src)
    assert r["success"], r.get("error", "")
    assert "#(.P(1 : 2 : 3), .Q(4))" in r["output"]
    assert "#(.WIDTH(8), .DEPTH(16))" in r["output"]
    assert "#(Mode, IOWait)" in r["output"]
    assert r["idempotent"]
