"""tests/languages/verilog/test_2005_batch9.py — 层次化引用交错形态（形式化宽进）。

2026-08-28 缺口修复批次：`a[0].b` / `a.b[0].c` / `mem[i].field` 等
**成员与下标任意交错**的层次化引用表达式位支持（A.9.3 hierarchical_
identifier 的形式化宽进——tpc 只做语法接受 + 保真渲染，不做"a[0] 是哪个
实例、b 是不是其成员"的继承链语义解析，那是综合/仿真工具的职责）。

实现三件套：
    - HierExpr production 改交错（@Identifier (@HierMember|@HierSuffix)*），
      HierMember 渲染 `.b`、HierSuffix 渲染 `[0]`，parts 空分隔 join 保序
    - SelectExpr exclude symbol.base.dot：纯下标不吞成员访问（a[0].b 回滚
      给 HierExpr）；choice 顺序 SelectExpr 在前、纯 a[0] 形状不变
    - 原子最长匹配（parser._atom_parser_impl + linter match_atom）：等长
      取先（a[0] 仍走 SelectExpr），交错形态 HierExpr 更长胜出

连带修复（同机制既有缺陷）：lookahead Level 1 判别路径被层级引用 `.`
挡住时回退 Level 2 全候选——`always @(*) a.b <= x;`（NBA target 为层级
引用）此前被误判未识别（linter/lookahead.py）。
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


def _flat(text: str) -> str:
    return "".join(text.split())


# ── RHS 交错形态（A.9.3 形式化宽进） ────────────────────────────────


def test_rhs_member_after_index():
    """`a[0].b`（成员在下标后）RHS 解析 + 渲染保真。"""
    src = "module m;\n    assign x = a[0].b;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "x=a[0].b;" in _flat(r.get("output", ""))


def test_rhs_member_between_indexes():
    """`a.b[0].c`（下标在成员间）RHS 解析 + 渲染保真。"""
    src = "module m;\n    assign x = a.b[0].c;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "x=a.b[0].c;" in _flat(r.get("output", ""))


def test_rhs_array_field():
    """`mem[i].field`（数组元素成员访问）RHS 解析。"""
    src = "module m;\n    assign x = mem[i].field;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "x=mem[i].field;" in _flat(r.get("output", ""))


def test_rhs_fully_interleaved():
    """`a[0].b[1].c`（多段交错）RHS 解析 + 顺序保真。"""
    src = "module m;\n    assign x = a[0].b[1].c;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "x=a[0].b[1].c;" in _flat(r.get("output", ""))


def test_rhs_inside_select_suffix():
    """交错形态嵌套在别的下标内（`y[a[0].b]`）。"""
    src = "module m;\n    assign x = y[a[0].b];\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "x=y[a[0].b];" in _flat(r.get("output", ""))


# ── LHS 交错形态 ─────────────────────────────────────────────────────


def test_lhs_continuous_assign_member_after_index():
    """`assign a[0].b = 1;`（连续赋值目标位）。"""
    src = "module m;\n    assign a[0].b = 1;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "a[0].b=1;" in _flat(r.get("output", ""))


def test_lhs_nba_arraymember():
    """`mem[i].field <= x;`（非阻塞赋值目标位）。"""
    src = "module m;\n    always @(*) mem[i].field <= x;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "mem[i].field<=x;" in _flat(r.get("output", ""))


def test_lhs_nba_hier_existing_defect():
    """既有缺陷回归：`a.b <= x;`（NBA target 为层级引用，无下标）。"""
    src = "module m;\n    always @(*) a.b <= x;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "a.b<=x;" in _flat(r.get("output", ""))


def test_lhs_blocking_hier():
    """`a.b = x;`（阻塞赋值目标位层级引用）。"""
    src = "module m;\n    always @(*) a.b = x;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "a.b=x;" in _flat(r.get("output", ""))


# ── 既有形态回归（形状稳定） ─────────────────────────────────────────


def test_plain_select_unchanged():
    """纯下标 `a[0]` / `a[0][1]` 仍正常（SelectExpr 先匹配）。"""
    src = (
        "module m;\n"
        "    assign x = a[0];\n"
        "    assign y = a[0][1];\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"]
    out = _flat(r.get("output", ""))
    assert "x=a[0];" in out and "y=a[0][1];" in out


def test_plain_hier_unchanged():
    """纯成员链 `a.b` / `a.b.c[3:0]` 仍正常（HierExpr 标准形态）。"""
    src = (
        "module m;\n"
        "    assign x = a.b;\n"
        "    assign y = a.b.c[3:0];\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"]
    out = _flat(r.get("output", ""))
    assert "x=a.b;" in out and "y=a.b.c[3:0];" in out


def test_typed_ports_coexist():
    """typed_ports 声明位点语法（spi.slave）不受表达式位增强影响。"""
    src = "module spi (spi.slave spi_io);\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "spi.slavespi_io" in _flat(r.get("output", ""))


def test_idempotent_interleaved():
    """交错形态输出再走一遍管线稳定（幂等）。"""
    src = "module m;\n    assign x = a[0].b[1].c;\nendmodule\n"
    r1 = _run(src)
    assert r1["success"]
    out1 = r1.get("output", "")
    r2 = _run(out1)
    assert r2["success"]
    assert _flat(r2.get("output", "")) == _flat(out1)
