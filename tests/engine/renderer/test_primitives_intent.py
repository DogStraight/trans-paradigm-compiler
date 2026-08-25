"""intent 原语测试（ADR-0006 阶段 4a 布局意图声明化）。

意图词表：compact（紧凑列表）/ wrap（流式折行）/ align（对齐）/
anchor（行尾锚定）。验证 intent 声明 → Doc 推导，且与等价手拼
（join/line_suffix/align）输出一致。
"""

from core.define import Node
from renderer.doc import Align, LineSuffix, layout
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


class TestIntentRegistered:
    def test_registered(self):
        keys = [k for k, _ in get_registry()]
        assert "intent" in keys


class TestIntentCompact:
    def test_compact_flat(self):
        """compact：列表一行（逗号分隔）。

        前导空格来自 first_soft=True（join 既有语义：flat 下首项前
        SoftLine→空格，broken 下换行+缩进）——intent 是 join 别名，
        行为与手拼一致。
        """
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("List", items=[a, b])
        expr = {"intent": "compact", "items": "items"}
        assert _render_expr(expr, node) == " a, b"

    def test_compact_matches_join(self):
        """compact 输出与等价 join 手拼一致（别名验证）。"""
        a = _n("id", value="aa")
        b = _n("id", value="bb")
        c = _n("id", value="cc")
        node = _n("List", items=[a, b, c])
        intent = {"intent": "compact", "items": "items"}
        manual = {
            "join": ", ",
            "items": "items",
            "first_soft": True,
            "nest": 1,
        }
        assert _render_expr(intent, node) == _render_expr(manual, node)

    def test_compact_custom_sep(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("List", items=[a, b])
        expr = {"intent": "compact", "items": "items", "sep": " | "}
        assert _render_expr(expr, node) == " a | b"


class TestIntentWrap:
    def test_wrap_flat(self):
        """wrap：全放得下 → 空格分隔单行。"""
        a = _n("id", value="aaaa")
        b = _n("id", value="bbbb")
        c = _n("id", value="cccc")
        node = _n("List", items=[a, b, c])
        expr = {"intent": "wrap", "items": "items"}
        assert _render_expr(expr, node, width=40) == "aaaa bbbb cccc"

    def test_wrap_breaks(self):
        """wrap：窄宽度 → 折行（中间态）。"""
        a = _n("id", value="aa")
        b = _n("id", value="bb")
        c = _n("id", value="cc")
        node = _n("List", items=[a, b, c])
        expr = {"intent": "wrap", "items": "items"}
        out = _render_expr(expr, node, width=6)
        assert out.split("\n") == ["aa bb", "cc"]


class TestIntentAlign:
    def test_align_returns_align_doc(self):
        """align：推导为 Align(align, doc)。"""
        node = _n("Pair", a=_n("id", value="x"), b=_n("id", value="y"))
        expr = {"intent": "align", "align": 2, "doc": {"ref": "a"}}
        r = _make_fake_renderer()
        doc = eval_expr(expr, node, None, r)
        assert isinstance(doc, Align)
        assert doc.align == 8

    def test_align_renders(self):
        node = _n("Pair", a=_n("id", value="x"), b=_n("id", value="y"))
        expr = {"intent": "align", "align": 2, "doc": {"ref": "a"}}
        assert _render_expr(expr, node) == "x"


class TestIntentAnchor:
    def test_anchor_returns_line_suffix(self):
        """anchor：推导为 LineSuffix(text)。"""
        node = _n("X")
        r = _make_fake_renderer()
        doc = eval_expr({"intent": "anchor", "text": " // note"}, node, None, r)
        assert isinstance(doc, LineSuffix)
        assert doc.text == " // note"
