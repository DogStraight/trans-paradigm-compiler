"""tests/languages/verilog/test_pratt_comment_keep.py — pratt 表达式内注释保留。

P1.5 修复（pratt 前缀吞注释）：pratt 前缀位置跳过行内注释（`a + /* c */ b`
的 `/* c */`、`- /* c */ a`、`cond ? /* c */ a : b`）时曾直接丢弃——注释
不纳 AST 也不进任何通道，渲染后丢失。修复（P1.5）：前缀跳注释经
comment_sink 进 parser._comment_anchors（midline 条目，锚 = 注释前
token）。
ADR-0013 决策 5（2026-09-04 落地）：operator 间隙注释在 pratt 循环跳过时
收集，挂到 BinaryOp/TernaryOp/UnaryOp 节点 `_comment_slots["inline_after"]`
（锚 = operator）——注释进 AST 元信息，renderer 结构序消费（line 原语 ref
属性锚匹配），锚点通道不再收 operator 间隙注释。

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
    """赋值 RHS 前缀注释保留（锚 = `=`，渲染在 `=` 与 `b` 之间）。"""
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


def test_comment_mounted_on_binary_op():
    """pratt operator 间隙注释挂 BinaryOp 节点（ADR-0013 决策 5）——
    不再进锚点通道：注释 = AST 节点元信息（inline_after，锚 = operator），
    renderer 结构序消费（layout 里 ref op 元素后），渲染后锚点通道为空。"""
    src = "module m;\n    assign x = a + /* 锚点 */ b;\nendmodule\n"
    r = _run(src)
    parser = r.get("parser")
    if parser is None:
        pytest.skip("parser 未挂到结果")
    # 锚点通道无此注释（结构序轨优先，双轨不双份）
    anchors = getattr(parser, "_comment_anchors", None) or []
    hits = [a for a in anchors if "锚点" in a.get("text", "")]
    assert not hits, "pratt operator 间隙注释不应进锚点通道（挂 BinaryOp 节点）"
    # 渲染后注释保留在 + 与 b 之间
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


def _find_node(node, name, out=None):
    """深度收集指定节点名（属性树 + 子节点）。"""
    if out is None:
        out = []
    if node is None:
        return out
    if getattr(node, "node_name", None) == name:
        out.append(node)
    import core.define as _cd

    for k, v in list(vars(node).items()):
        if k.startswith("_"):
            continue
        if isinstance(v, _cd.Node):
            _find_node(v, name, out)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, _cd.Node):
                    _find_node(item, name, out)
    return out


def test_operator_gap_comment_mounted_on_expr_node():
    """operator 间隙注释挂表达式节点元信息（ADR-0013 决策 5）：
    `a + /* c */ b` → BinaryOp._comment_slots.inline_after['+']；
    `- /* c */ a` → UnaryOp；`cond ? /* 真 */ a : /* 假 */ b` → TernaryOp
    （op1 '?' 与 op2 ':' 各自锚）。渲染前（analyzer/transform 关闭）断言
    节点元信息，而非仅渲染文本。"""
    from pipeline import run_pipeline_on_source

    cases = [
        (
            "module m;\n    assign x = a + /* 锚 */ b;\nendmodule\n",
            "BinaryOp",
            {"inline_after": {"+": [("/* 锚 */", 2)]}},
        ),
        (
            "module m;\n    assign x = - /* 负 */ a;\nendmodule\n",
            "UnaryOp",
            {"inline_after": {"-": [("/* 负 */", 2)]}},
        ),
        (
            "module m;\n    assign x = c ? /* 真 */ a : /* 假 */ b;\nendmodule\n",
            "TernaryOp",
            {
                "inline_after": {
                    "?": [("/* 真 */", 2)],
                    ":": [("/* 假 */", 2)],
                }
            },
        ),
    ]
    for src, node_name, expect_slots in cases:
        r = run_pipeline_on_source(
            source=src, rules_dir="grammar/verilog", quiet=True, no_lint=True,
            renderer_enabled=False, analyzer_enabled=False,
            transform_enabled=False, format_output=False, expand_macros=False,
        )
        assert not r.get("error"), r.get("error", "")  # renderer-off 时 success 恒 False（render 阶段置位）
        found = _find_node(r.get("ast"), node_name)
        assert found, f"{node_name} 未解析出"
        mounted = [
            getattr(n, "_comment_slots", None) for n in found
            if getattr(n, "_comment_slots", None)
        ]
        assert any(s == expect_slots for s in mounted), (
            f"{node_name} 注释未按 ADR-0013 挂载: {mounted!r}"
        )


# ── 方向 B：operator 行尾注释（ADR-0014 ②，darkriscv BMUX 5 条） ──
# `a || // c\n b`——`//` 行尾注释在 operator 间隙：渲染重排后无安全落点，
# 方向 B 挂后续 RHS 子节点 leading（_comment_slots["leading"]），输出强制
# 断行 `a || // c\nb`——机械安全（// 必在行尾），语义近似（注释在 op 与
# 下段之间）。


def test_binary_op_eol_comment_kept():
    """BinaryOp 行尾注释保留且落在 op 与 RHS 之间（darkriscv `|| // bgeu`）。"""
    src = "module m;\n    assign x = a || // 条件\n        b;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    out = r.get("output", "")
    assert "// 条件" in out
    assert "a || // 条件" in out  # 注释留 op 行尾
    assert "b" in out


def test_ternary_colon_eol_comment_kept():
    """Ternary `:` 后行尾注释保留（tv80/darkriscv `: // misc` 存活形态）。"""
    src = "module m;\n    assign x = c ? a : // 假分支\n        b;\nendmodule\n"
    r = _run(src)
    assert r["success"]
    out = r.get("output", "")
    assert "// 假分支" in out
    assert "c ? a : // 假分支" in out


def test_operator_eol_comment_mounted_on_rhs_leading():
    """行尾注释挂后续 RHS 子节点 leading（ADR-0014 方向 B 元信息断言）——
    BinaryOp `a || // c\n b` → right（b）leading 槽含注释。"""
    from pipeline import run_pipeline_on_source

    src = "module m;\n    assign x = a || // 方向B\n        b;\nendmodule\n"
    r = run_pipeline_on_source(
        source=src, rules_dir="grammar/verilog", quiet=True, no_lint=True,
        renderer_enabled=False, analyzer_enabled=False,
        transform_enabled=False, format_output=False, expand_macros=False,
    )
    assert not r.get("error"), r.get("error", "")
    # BinaryOp.right 的 leading 槽含该注释
    bins = _find_node(r.get("ast"), "BinaryOp")
    assert bins, "BinaryOp 未解析出"
    found = False
    for n in bins:
        right = getattr(n, "right", None)
        slots = getattr(right, "_comment_slots", None) if right is not None else None
        if slots and "leading" in slots and any(
            "方向B" in c for c in slots["leading"]
        ):
            found = True
            break
    assert found, "行尾注释未挂到 RHS leading 槽"


def test_operator_eol_comment_idempotent():
    """方向 B 输出再走一遍管线注释仍保留（幂等，防振荡）。"""
    src = "module m;\n    assign x = a || // 幂等B\n        b;\nendmodule\n"
    r1 = _run(src)
    assert r1["success"]
    out1 = r1.get("output", "")
    assert "// 幂等B" in out1
    r2 = _run(out1)
    assert r2["success"]
    assert "// 幂等B" in r2.get("output", "")
