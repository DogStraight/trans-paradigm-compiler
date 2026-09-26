"""渲染器引擎级 raw 拼接（`_verbatim_text`）——宏调用视为不可拆原子文本。

节点带引擎标记 `_verbatim_text` 时整体直出该文本：不走布局、不遍历子节点。
语言包对宏零知识，本规则是引擎协议（ADR-0017 决策 4）。

另有两条判据守"直出切片与注释槽的边界"（2026-09-26 实测缺陷）：切片**内**的注释已随切片
输出、槽不得再吐一份；切片**外**的附着槽仍必须输出。
"""

import pytest

from core.define import Node
from core.define import DEFAULT_RULES_DIR
from renderer.doc import Concat, HardBreak, Text, layout
from renderer.node_renderer import render_node
from renderer.renderer import Renderer


@pytest.fixture(scope="module")
def renderer():
    return Renderer(DEFAULT_RULES_DIR)


def test_verbatim_replaces_subtree(renderer) -> None:
    """带标记的节点：子节点不渲染，只出标记文本。"""
    node = Node("Identifier", content="should_not_appear")
    node.add_attr("_verbatim_text", "`MACRO")
    assert renderer.render(node).strip() == "`MACRO"


def test_verbatim_inside_parent_layout(renderer) -> None:
    """父布局照常渲染：标记节点的原文成为它所在位置的原子文本。"""
    inner = Node("Number", value="8")
    inner.add_attr("_verbatim_text", "`W")
    node = Node("ParenthesizedExpr", expr=inner)
    out = renderer.render(node)
    assert "`W" in out
    assert "8" not in out


def test_verbatim_multiline_kept_as_is(renderer) -> None:
    """多行原文原样保留（不做重排）——"宁可原样，不可静默重排"。"""
    node = Node("Identifier", content="x")
    node.add_attr("_verbatim_text", "`BODY a = 1;\n  b = 2;")
    out = renderer.render(node)
    assert "a = 1;" in out and "b = 2;" in out
    assert "\n" in out


# ── 直出切片 vs 注释槽的边界（2026-09-26 实测缺陷）────────────────────────────

def _render_with_flush(renderer, node) -> str:
    """渲染直出节点并**制造 flush 条件**（LineSuffix 只在后续换行时才输出）。

    ⚠ 单节点渲染不 flush ⇒ 判据会"修前也绿"（本文件第一版就这么写错、复核时抓到）。
    故接一个 `HardBreak` + 后继文本。
    """
    doc = Concat([render_node(node, {}, renderer), HardBreak(), Text("next")])
    return layout(doc)


def test_comment_inside_verbatim_is_not_duplicated(renderer) -> None:
    """切片里已含的行尾注释，不再由注释槽重复输出（回归：语料实测每遍加倍）。

    事故：语句含宏 ⇒ `_stage_macro_splice` 挂 `_verbatim_text` = 该语句的**展开切片**，
    而切片末尾**就含行尾注释**（实测现场切片尾部 `… } ; // i-type `，732 字符）；同一条
    注释又在 `_comment_slots['trailing']` 里（**裸 str**）。`_render_verbatim` 按 docstring
    的假设"附着注释在节点 span **之外**，故槽仍要输出"⇒ 一条注释出两份；下一遍渲染切片里
    已含两份 ⇒ **每遍加倍**（实测 `// i-type` 4→6→10、注释总数 731→733→737、且不收敛）。

    判据按**完整输出**断言：修前多出的那份是槽的 LineSuffix，其渲染形态会被拉开
    （`/ /   c 1`），按 `// c1` 计数同样看不出——只有整串比对抓得住。
    """
    node = Node("AssignStmt")
    node.add_attr("_verbatim_text", "x = `M + 1 ; // c1 ")
    node.add_attr("_comment_slots", {"trailing": "// c1 "})

    assert _render_with_flush(renderer, node) == "x = `M + 1 ; // c1 \nnext"


def test_comment_outside_verbatim_is_still_emitted(renderer) -> None:
    """对照：切片**之外**的注释槽仍必须输出（否则附着注释静默丢失）。

    `_render_verbatim` docstring 明确要求保留切片外的附着槽（前置槽亦然）。本判据守住修法
    的边界：只丢"确实已在切片里"的那些，不许一刀切。
    """
    node = Node("AssignStmt")
    node.add_attr("_verbatim_text", "x = `M + 1 ;")
    node.add_attr("_comment_slots", {"trailing": "// keep-me "})

    out = _render_with_flush(renderer, node)

    assert "k e e p - m e" in out, f"切片外的注释槽被误丢：{out!r}"
