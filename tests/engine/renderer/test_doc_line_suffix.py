"""LineSuffix（行尾锚定）测试（ADR-0006 阶段 2）。

验证 _resolve_line_suffix 的推迟语义：suffix 内容锚定在下一个
换行点之前（行尾注释），与 Prettier lineSuffix 一致。
"""

from core.define import Node
from renderer.doc import (
    Break,
    Concat,
    Line,
    LineSuffix,
    Text,
    layout,
)
from renderer.primitives import eval_expr, get_registry

from test_renderer_primitives import _make_fake_renderer


class TestLineSuffixDoc:
    def test_suffix_before_line(self):
        """Concat([a, LineSuffix, b, Line, c]) → 'a b // note\nc'。"""
        doc = Concat(
            [
                Text("a"),
                LineSuffix(" // note"),
                Text(" b"),
                Line(),
                Text("c"),
            ]
        )
        assert layout(doc) == "a b // note\nc"

    def test_suffix_at_doc_end(self):
        """无换行点时 suffix 追加到 doc 末尾。"""
        doc = Concat([Text("a"), LineSuffix(" // note")])
        assert layout(doc) == "a // note"

    def test_suffix_multiple_accumulate(self):
        doc = Concat(
            [Text("a"), LineSuffix(" // x"), LineSuffix(" // y"), Line(), Text("b")]
        )
        assert layout(doc) == "a // x // y\nb"

    def test_suffix_in_flat_group(self):
        """group flat 模式：LineSuffix 直接显示（跟在行尾）。"""
        from renderer.doc import group

        doc = group(
            Concat([Text("a"), LineSuffix(" // note"), Line(), Text("b")])
        )
        # flat：'a // note b'（suffix 就地，line 变空格）
        assert layout(doc, 80) == "a // note b"

    def test_suffix_in_broken_group(self):
        """group broken 模式：suffix 锚定行尾。"""
        from renderer.doc import group

        doc = group(
            Concat([Text("a"), LineSuffix(" // note"), Line(), Text("b")])
        )
        assert layout(doc, 5) == "a // note\nb"

    def test_suffix_after_break(self):
        """suffix 出现在 Break 之后 → 不推迟（已在行首区）。"""
        doc = Concat([Text("a"), Break(), Text("b"), LineSuffix(" // note")])
        assert layout(doc) == "a\nb // note"


class TestLineSuffixPrimitive:
    def test_registered(self):
        keys = [k for k, _ in get_registry()]
        assert "line_suffix" in keys

    def test_line_suffix_expr(self):
        """{line_suffix: " // note"} → LineSuffix。"""
        node = Node("X")
        r = _make_fake_renderer()
        doc = eval_expr({"line_suffix": " // note"}, node, None, r)
        assert isinstance(doc, LineSuffix)
        assert doc.text == " // note"
