"""align/fill 原语 TOML 表达式层测试（ADR-0006 阶段 2）。

验证 eval_expr 对 {align: N, doc: ...} 与 {fill: [...]} 的求值，
以及原语注册表包含 align/fill。
"""

from core.define import Node
from renderer.doc import Align, Fill, Text, layout
from renderer.primitives import eval_expr, get_registry

from test_renderer_primitives import _make_fake_renderer


def _render_expr(expr, node, width=80):
    r = _make_fake_renderer()
    doc = eval_expr(expr, node, parent_layout=None, renderer=r)
    if doc is None:
        return ""
    return layout(doc, width)


def _n(node_name, **kw):
    return Node(node_name, **kw)


class TestAlignPrimitive:
    def test_registered(self):
        keys = [k for k, _ in get_registry()]
        assert "align" in keys

    def test_align_expr(self):
        """{align: 2, doc: {line: [{ref}, {soft}, {ref}]}} → Align(8, ...)"""
        node = _n("Pair", a=_n("id", value="x"), b=_n("id", value="y"))
        expr = {"align": 2, "doc": {"line": [{"ref": "a"}, {"soft": True}, {"ref": "b"}]}}
        r = _make_fake_renderer()
        doc = eval_expr(expr, node, None, r)
        assert isinstance(doc, Align)
        assert doc.align == 8  # 2 级 × 4 格

    def test_align_missing_inner(self):
        node = _n("Pair")
        assert _render_expr({"align": 2, "doc": {"ref": "missing"}}, node) == ""


class TestFillPrimitive:
    def test_registered(self):
        keys = [k for k, _ in get_registry()]
        assert "fill" in keys

    def test_fill_expr_flat(self):
        """{fill: [{ref}, {soft}, {ref}]} 全部放得下 → 单行空格分隔。"""
        node = _n("Pair", a=_n("id", value="aaa"), b=_n("id", value="bbb"))
        expr = {"fill": [{"ref": "a"}, {"soft": True}, {"ref": "b"}]}
        r = _make_fake_renderer()
        doc = eval_expr(expr, node, None, r)
        assert isinstance(doc, Fill)
        assert _render_expr(expr, node) == "aaa bbb"

    def test_fill_expr_breaks(self):
        """窄宽度下 fill 折行。"""
        node = _n("Triple",
                  a=_n("id", value="aa"), b=_n("id", value="bb"), c=_n("id", value="cc"))
        expr = {"fill": [
            {"ref": "a"}, {"soft": True},
            {"ref": "b"}, {"soft": True},
            {"ref": "c"},
        ]}
        out = _render_expr(expr, node, width=6)
        assert out.split("\n") == ["aa bb", "cc"]

    def test_fill_text_items(self):
        node = _n("X")
        expr = {"fill": ["a", {"soft": True}, "b"]}
        assert _render_expr(expr, node) == "a b"
