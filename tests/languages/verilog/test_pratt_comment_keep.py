"""tests/languages/verilog/test_pratt_comment_keep.py — pratt 表达式内注释保留。

P1.5 修复（pratt 前缀吞注释）：pratt 前缀位置跳过行内注释（`a + /* c */ b`
的 `/* c */`、`- /* c */ a`、`cond ? /* c */ a : b`）时曾直接丢弃——注释
不纳 AST 也不进任何通道，渲染后丢失。修复：前缀跳注释经 comment_sink 进
parser._comment_anchors（midline 条目，锚 = 注释前 token），渲染后
restore only_midline 回插兜底（注释节点模型 2b-2 双轨语义，与
`assign b = /* 嵌入 */ rst_n` 的 inline_after 路径互补）。

覆盖形态：
    - 中缀右操作数前：`a + /* c */ b`
    - 赋值 RHS 前缀：`assign x = /* c */ b`
    - 一元前缀操作数前：`- /* c */ a`
    - 三目 true/false 分支：`cond ? /* c */ a : /* d */ b`
    - 中缀左操作数后（外层机制，回归守卫）：`a /* c */ + b`
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src, **kw):
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


def _flat(text: str) -> str:
    return "".join(text.split())


def test_infix_rhs_comment_kept():
    """中缀右操作数前注释保留且落在原语义位置（`+` 与 `b` 之间）。"""
    src = "module m;\n    assign x = a + /* 中缀后 */ b;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    out = _flat(r.get("output", ""))
    assert "a+/*中缀后*/b" in out
    # 注释不得被行尾化（attachment 语义）
    assert not out.rstrip().endswith("/*中缀后*/")


def test_assign_rhs_prefix_comment_kept():
    """赋值 RHS 前缀注释保留（锚 = `=`，回插到 `=` 与 `b` 之间）。"""
    src = "module m;\n    assign x = /* 前缀 */ b;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "/*前缀*/b" in _flat(r.get("output", ""))


def test_unary_prefix_operand_comment_kept():
    """一元前缀操作数前注释保留（`-` 与 `a` 之间）。"""
    src = "module m;\n    assign x = - /* 负号后 */ a;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "-/*负号后*/a" in _flat(r.get("output", ""))


def test_ternary_true_branch_comment_kept():
    """三目 true 分支注释保留（锚 = `?`）。"""
    src = (
        "module m;\n"
        "    assign x = cond ? /* 真 */ a : b;\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"]
    assert "cond?/*真*/a:b" in _flat(r.get("output", ""))


def test_ternary_false_branch_comment_kept():
    """三目 false 分支注释保留（锚 = `:`）。"""
    src = (
        "module m;\n"
        "    assign x = cond ? a : /* 假 */ b;\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"]
    assert "cond?a:/*假*/b" in _flat(r.get("output", ""))
    # 注：同行多注释（`cond ? /* 真 */ a : /* 假 */ b`）受 restore 单行单插
    # 局限（第二条退化行尾），属既有能力边界，不在本修复范围（修复前
    # pratt 吞注释是直接丢失）。


def test_infix_lhs_comment_kept():
    """中缀左操作数后注释（外层机制收集，回归守卫不丢失）。"""
    src = "module m;\n    assign x = a /* 中缀前 */ + b;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    assert "a/*中缀前*/+b" in _flat(r.get("output", ""))


def test_comment_survives_idempotent_rerun():
    """输出再走一遍管线注释仍保留（幂等性，防回插振荡）。"""
    src = "module m;\n    assign x = a + /* 幂等 */ b;\nendmodule\n"
    r1 = _run(src)
    assert r1["success"]
    out1 = r1.get("output", "")
    r2 = _run(out1)
    assert r2["success"]
    assert _flat(r2.get("output", "")) == _flat(out1)


def test_comment_recorded_in_anchor_channel():
    """pratt 吞掉的注释进锚点通道（midline 条目，锚 = 注释前 token）。"""
    src = "module m;\n    assign x = a + /* 锚点 */ b;\nendmodule\n"
    r = _run(src)
    parser = r.get("parser")
    if parser is None:
        pytest.skip("parser 未挂到结果")
    anchors = getattr(parser, "_comment_anchors", None) or []
    hits = [a for a in anchors if "锚点" in a.get("text", "")]
    assert hits, "pratt 跳过注释应记录到锚点通道"
    entry = hits[0]
    assert entry.get("midline") is True
    assert entry.get("anchor") == "+"
    # 渲染后回插（输出含注释）且锚点通道条目仍可查（双轨去重不删源）
    assert "/*锚点*/b" in _flat(r.get("output", ""))


def test_comment_kept_in_case_expression():
    """case 比较表达式内注释保留（原子/选择表达式组合场景）。"""
    src = (
        "module m;\n"
        "    always @(*) case (sel)\n"
        "        2'b00: y = a && /* 与 */ b;\n"
        "        default: y = 0;\n"
        "    endcase\n"
        "endmodule\n"
    )
    r = _run(src)
    assert r["success"]
    assert "a&&/*与*/b" in _flat(r.get("output", ""))
