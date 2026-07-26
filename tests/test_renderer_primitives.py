"""Renderer 原语行为测试 — 直接调用 eval_expr + 最小 fake renderer。

不加载任何 TOML 布局文件，不依赖解析器。
手动构造 Node + 布局 expr dict，验证渲染原语输出。
"""

import pytest
from core.define import Node
from renderer.doc import Doc, layout
from renderer.primitives import eval_expr
from renderer.primitives.text import eval_text
from renderer.doc import Text, Empty


def _make_fake_renderer():
    """创建最小 fake renderer，供原语回调使用。"""

    class FakeRenderer:
        _INDENT_STR = "    "
        _layouts = {}

        def _render_inline(self, child_node, layout_cfg, indent):
            val = getattr(child_node, "value", None)
            if val is not None:
                return Text(str(val))
            return Text(child_node.node_name)

        def _get_merged_layout(self, parent_layout, child_name):
            return {}

        def _resolve_items(self, node, items_spec):
            if isinstance(items_spec, str):
                return getattr(node, items_spec, [])
            return []

        def _eval(self, expr, node, indent, parent_layout=None):
            return eval_expr(expr, node, indent, parent_layout, self)

    return FakeRenderer()


def _render_expr(expr, node):
    r = _make_fake_renderer()
    doc = eval_expr(expr, node, indent=0, parent_layout=None, renderer=r)
    if doc is None:
        return ""
    return layout(doc)


def _n(node_name, **kw):
    return Node(node_name, **kw)


# ═══════════════════════════════════════════════════════
# text 原语
# ═══════════════════════════════════════════════════════

class TestTextPrimitive:
    def test_str_expr_returns_text(self):
        r = _make_fake_renderer()
        doc = eval_expr("hello", _n("x"), 0, None, r)
        assert isinstance(doc, Text)
        assert doc.text == "hello"

    def test_str_expr_renders(self):
        assert _render_expr("world", _n("x")) == "world"

    def test_non_dict_non_str_fallback(self):
        r = _make_fake_renderer()
        doc = eval_expr(42, _n("x"), 0, None, r)
        assert isinstance(doc, Text)
        assert doc.text == "42"


# ═══════════════════════════════════════════════════════
# ref 原语
# ═══════════════════════════════════════════════════════

class TestRefPrimitive:
    def test_ref_value_attr(self):
        node = _n("Keyword", value="wire")
        assert _render_expr({"ref": "value"}, node) == "wire"

    def test_ref_missing_attr(self):
        node = _n("Keyword")
        assert _render_expr({"ref": "nonexistent"}, node) == ""

    def test_ref_with_child_node(self):
        child = _n("Ident", value="x")
        parent = _n("Decl", name=child)
        assert _render_expr({"ref": "name"}, parent) == "x"


# ═══════════════════════════════════════════════════════
# line 原语
# ═══════════════════════════════════════════════════════

class TestLinePrimitive:
    def test_line_concat(self):
        node = _n("Pair", a=_n("id", value="x"), b=_n("id", value="y"))
        expr = {"line": [{"ref": "a"}, {"ref": "b"}]}
        assert _render_expr(expr, node) == "xy"

    def test_line_with_soft_break(self):
        node = _n("Pair", a=_n("id", value="hello"), b=_n("id", value="world"))
        expr = {"line": [{"ref": "a"}, {"soft": True}, {"ref": "b"}]}
        assert _render_expr(expr, node) == "hello world"

    def test_line_with_text_mixed(self):
        node = _n("Keyword", value="wire")
        expr = {"line": [{"ref": "value"}, " ;"]}
        assert _render_expr(expr, node) == "wire ;"

    def test_line_single_item(self):
        node = _n("id", value="just_me")
        assert _render_expr({"line": [{"ref": "value"}]}, node) == "just_me"


# ═══════════════════════════════════════════════════════
# join 原语
# ═══════════════════════════════════════════════════════

class TestJoinPrimitive:
    def test_join_two_items(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("List", items=[a, b])
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == "a, b"

    def test_join_single_item(self):
        a = _n("id", value="only")
        node = _n("List", items=[a])
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == "only"

    def test_join_empty(self):
        node = _n("List", items=[])
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == ""


# ═══════════════════════════════════════════════════════
# group 原语
# ═══════════════════════════════════════════════════════

class TestGroupPrimitive:
    def test_group_flat(self):
        node = _n("id", value="short")
        expr = {"group": [{"ref": "value"}]}
        assert _render_expr(expr, node) == "short"

    def test_group_with_line(self):
        node = _n("Pair", a=_n("id", value="a"), b=_n("id", value="b"))
        expr = {"group": [{"line": [{"ref": "a"}, {"soft": True}, {"ref": "b"}]}]}
        assert _render_expr(expr, node) == "a b"


# ═══════════════════════════════════════════════════════
# opt 原语
# ═══════════════════════════════════════════════════════

class TestOptPrimitive:
    def test_opt_present(self):
        node = _n("Labelled", label=_n("Keyword", value="LABEL:"))
        expr = {"opt": {"ref": "label"}}
        assert _render_expr(expr, node) == "LABEL:"

    def test_opt_absent(self):
        node = _n("Labelled")
        expr = {"opt": {"ref": "label"}}
        assert _render_expr(expr, node) == ""


# ═══════════════════════════════════════════════════════
# 组合
# ═══════════════════════════════════════════════════════

class TestCombined:
    def test_line_with_opt(self):
        node = _n("Labelled",
                   label=_n("Keyword", value="tag:"),
                   value=_n("id", value="data"))
        expr = {"line": [
            {"opt": {"ref": "label"}},
            " ",
            {"ref": "value"},
        ]}
        assert _render_expr(expr, node) == "tag: data"

    def test_join_in_line(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("Container", items=[a, b], name=_n("id", value="result"))
        expr = {"line": [
            {"ref": "name"},
            " = ",
            {"join": ", ", "items": "items"},
        ]}
        assert _render_expr(expr, node) == "result = a, b"
