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


# ── 交错形态用例表（A.9.3 形式化宽进） ──────────────────────────────
# 全部用例同构：喂一段源码，断言管线成功 + 渲染后的扁平文本含期望片段。
# 新形态只加一行 param——不再复制一份测试函数（原来 9 个同构函数）。
_CASES = [
    pytest.param(
        "module m;\n    assign x = a[0].b;\nendmodule\n", "x=a[0].b;",
        id="rhs_member_after_index"),
    pytest.param(
        "module m;\n    assign x = a.b[0].c;\nendmodule\n", "x=a.b[0].c;",
        id="rhs_member_between_indexes"),
    pytest.param(
        "module m;\n    assign x = mem[i].field;\nendmodule\n", "x=mem[i].field;",
        id="rhs_array_field"),
    pytest.param(
        "module m;\n    assign x = a[0].b[1].c;\nendmodule\n", "x=a[0].b[1].c;",
        id="rhs_fully_interleaved"),
    pytest.param(
        "module m;\n    assign x = y[a[0].b];\nendmodule\n", "x=y[a[0].b];",
        id="rhs_inside_select_suffix"),
    pytest.param(
        "module m;\n    assign a[0].b = 1;\nendmodule\n", "a[0].b=1;",
        id="lhs_continuous_assign_member_after_index"),
    pytest.param(
        "module m;\n    always @(*) mem[i].field <= x;\nendmodule\n", "mem[i].field<=x;",
        id="lhs_nba_arraymember"),
    pytest.param(
        "module m;\n    always @(*) a.b <= x;\nendmodule\n", "a.b<=x;",
        id="lhs_nba_hier_existing_defect"),
    pytest.param(
        "module m;\n    always @(*) a.b = x;\nendmodule\n", "a.b=x;",
        id="lhs_blocking_hier"),
]


@pytest.mark.parametrize("src,expect", _CASES)
def test_interleaved_hier_ref_forms(src, expect):
    """层次化引用「成员 / 下标任意交错」在各位置均解析 + 渲染保真。

    覆盖 RHS 表达式位与 LHS 赋值目标位（连续赋值 / 非阻塞 / 阻塞），
    以及嵌套在别的下标内的形态。
    """
    r = _run(src)
    assert r["success"], "解析失败"
    assert expect in _flat(r.get("output", "")), "渲染不保真"


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
    """typed_ports 声明位点语法（spi.slave）不受表达式位增强影响。

    语法共存用保留路径（expand_enhanced=False）：本测试只验证声明位
    `spi.slave` 的 parse/渲染，不做 typed_ports 语义（无 type 定义片段
    在展开路径会触发 TP001——见 ADR-0013 analyzer postpass）。
    """
    src = "module spi (spi.slave spi_io);\nendmodule\n"
    r = _run(src, expand_enhanced=False)
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
