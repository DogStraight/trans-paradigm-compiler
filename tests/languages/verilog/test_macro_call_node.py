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
