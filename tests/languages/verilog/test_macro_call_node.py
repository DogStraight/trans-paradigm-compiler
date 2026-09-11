"""宏边界节点化（0.1.2 阶段 2-A）：marker 标识符 → MacroCall 节点，输出不变。

展开阶段宏调用被替换为 `tpc_marker_N` 标识符；引擎在 parse 后按锚表把 Identifier
节点改写为 MacroCall（带 `_macro_name`），使宏边界在 AST 结构化可见（P3.2 增量
diff / P3.3 双向映射前提）。本阶段渲染/分析声明与 Identifier 对齐 → 输出不变。
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke

_SRC = (
    "module m;\n"
    "`define W 8\n"
    "  wire [`W-1:0] a;\n"
    "`define BODY x = 1'b1;\n"
    "  reg x;\n"
    "  initial begin\n"
    "    `BODY\n"
    "  end\n"
    "endmodule\n"
)


def _run():
    return run_pipeline_on_source(
        source=_SRC, quiet=True, no_lint=True, expand_macros=True
    )


def _find(node, name: str) -> list:
    out: list = []

    def rec(n):
        if getattr(n, "node_name", None) == name:
            out.append(n)
        for child in n.iter_children():
            rec(child)

    rec(node)
    return out


def test_macro_call_nodes_created() -> None:
    """表达式位与语句位的宏调用都成为 MacroCall 节点（带宏名元数据）。"""
    res = _run()
    assert res["success"], res.get("error")
    calls = _find(res["ast"], "MacroCall")
    assert len(calls) == 2, [c._macro_name for c in calls]
    assert {c._macro_name for c in calls} == {"W", "BODY"}
    for c in calls:
        assert c._macro_marker.startswith("tpc_marker_")


def test_no_plain_identifier_left_for_marker() -> None:
    """marker 不再以普通 Identifier 形态留在 AST（边界已节点化）。"""
    res = _run()
    leftover = [
        n
        for n in _find(res["ast"], "Identifier")
        if str(getattr(n, "content", "")).startswith("tpc_marker_")
    ]
    assert leftover == []


def test_output_unchanged_macro_restored() -> None:
    """输出保真：无 marker 残留，宏调用原文还原。"""
    res = _run()
    out = res["output"]
    assert "tpc_marker" not in out
    assert "`W" in out
    assert "`BODY" in out


def test_no_macro_when_expansion_disabled() -> None:
    """未展开宏时不产生 MacroCall 节点（锚表为空 → 不改写）。"""
    src = "module m;\n  wire a;\nendmodule\n"
    res = run_pipeline_on_source(source=src, quiet=True, no_lint=True)
    assert res["success"], res.get("error")
    assert _find(res["ast"], "MacroCall") == []


def test_macro_src_span_points_at_source_call() -> None:
    """`_src_span` 精确指向**源文本**中的宏调用原文（ADR-0016 raw 源区间权威）。

    强校验：用 (line, col, end_col) 切源文本行，切片必须等于 `` `NAME ``。
    """
    res = _run()
    lines = _SRC.split("\n")
    calls = {c._macro_name: c for c in _find(res["ast"], "MacroCall")}
    assert set(calls) == {"W", "BODY"}
    for name, node in calls.items():
        assert node._src_span is not None, name
        line, col, end_col = node._src_span
        assert lines[line - 1][col:end_col] == f"`{name}", (name, node._src_span)


def test_macro_call_has_both_spans() -> None:
    """宏调用位 = 双区间：`_tok_span`（展开后 token 流）+ `_src_span`（源文本）。"""
    res = _run()
    for node in _find(res["ast"], "MacroCall"):
        assert node._tok_span is not None
        assert node._src_span is not None
        tok_start, tok_end = node._tok_span
        assert 0 <= tok_start < tok_end


def test_macro_body_attached() -> None:
    """完整单元宏的展开体子树挂在 `_macro_body`（MacroBody 包装，含标记）。"""
    res = _run()
    calls = {c._macro_name: c for c in _find(res["ast"], "MacroCall")}
    w = calls["W"]  # `define W 8 → 完整表达式
    assert w._macro_body is not None
    assert w._macro_body.node_name == "MacroBody"
    assert w._macro_body._from_expansion is True
    b = calls["BODY"]  # `define BODY x = 1'b1; → 完整语句
    assert b._macro_body is not None
    assert [k.node_name for k in b._macro_body.iter_children()] == ["BlockingAssign"]


def test_macro_body_not_in_children() -> None:
    """子树**不占 children**（渲染/语义遍历不进入）→ 行为面零变化。"""
    res = _run()
    for node in _find(res["ast"], "MacroCall"):
        assert list(node.iter_children()) == []
