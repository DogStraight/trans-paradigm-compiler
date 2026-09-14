"""渲染器引擎级 raw 拼接（`_verbatim_text`）——宏调用视为不可拆原子文本。

节点带引擎标记 `_verbatim_text` 时整体直出该文本：不走布局、不遍历子节点。
语言包对宏零知识，本规则是引擎协议（ADR-0017 决策 4）。
"""

import pytest

from core.define import Node
from core.define import DEFAULT_RULES_DIR
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
