"""Renderer Doc IR 单元测试 — layout 算法，不依赖 parser/lexer。"""

from renderer.doc import (
    Doc, Empty, Text, Line, LineBreak, Break,
    Concat, Nest, Prefix, Union,
    group, flatten, layout,
)
from renderer.doc import _fits, _fits_fixed_len  # noqa: E402  判据直测私有谓词（见文末回归类）


class TestDocConstruct:
    """Doc 类型构造和行为。"""

    def test_empty(self):
        assert isinstance(Empty(), Doc)
        assert layout(Empty()) == ""

    def test_text(self):
        assert layout(Text("hello")) == "hello"

    def test_concat(self):
        doc = Concat([Text("a"), Text("b")])
        assert layout(doc) == "ab"

    def test_line_flat(self):
        """未 group 的 Line 直接渲染为换行。"""
        doc = Concat([Text("a"), Line(), Text("b")])
        assert layout(doc) == "a\nb"

    def test_nest(self):
        """Nest 只影响内部的 Line。"""
        doc = Nest(2, Concat([Text("a"), Line(), Text("b")]))
        assert layout(doc) == "a\n  b"

    def test_prefix(self):
        doc = Prefix(4, Text("x"))
        assert layout(doc) == "    x"

    def test_hard_break(self):
        doc = Concat([Text("a"), Break(), Text("b")])
        assert layout(doc) == "a\nb"


class TestDocGroup:
    """group 和 flatten 控制 flat/broken 选择。"""

    def test_group_fits_on_one_line(self):
        """group 内内容能放下时不换行。"""
        doc = group(Concat([Text("hello"), Line(), Text("world")]))
        assert layout(doc, max_width=80) == "hello world"

    def test_group_broken_when_exceeds_width(self):
        """group 内内容超宽时换行。"""
        doc = group(Concat([Text("hello"), Line(), Text("world")]))
        assert layout(doc, max_width=5) == "hello\nworld"

    def test_flat_line_becomes_space(self):
        flat = flatten(Concat([Text("a"), Line(), Text("b")]))
        assert layout(flat) == "a b"

    def test_flat_linebreak_becomes_empty(self):
        flat = flatten(Concat([Text("a"), LineBreak(), Text("b")]))
        assert layout(flat) == "ab"

    def test_flat_is_idempotent(self):
        t = Text("x")
        assert flatten(flatten(t)) == flatten(t)

    def test_nested_group(self):
        """嵌套 group，外层 flat 时内层也 flat。"""
        inner = group(Concat([Text("inner"), Line(), Text("short")]))
        outer = group(Concat([Text("outer,"), Line(), inner]))
        result = layout(outer, max_width=80)
        assert " " in result

    def test_group_nested_broken(self):
        """外层 group broken 时内层也 broken。"""
        inner = group(Concat([Text("x"), Line(), Text("y")]))
        doc = group(Concat([Text("a"), Line(), inner]))
        result = layout(doc, max_width=3)
        assert result == "a\nx y"


class TestDocLayout:
    """layout 函数的边界情况和正确性。"""

    def test_empty_doc(self):
        assert layout(Empty()) == ""

    def test_only_text(self):
        assert layout(Text("hello")) == "hello"

    def test_line_at_start(self):
        doc = Concat([Line(), Text("x")])
        assert layout(doc) == "\nx"

    def test_consecutive_lines(self):
        doc = Concat([Text("a"), Line(), Line(), Text("b")])
        assert layout(doc) == "a\n\nb"

    def test_nest_affects_line_indent(self):
        doc = Concat([Text("a"), Line(), Nest(4, Concat([Text("b"), Line(), Text("c")]))])
        result = layout(doc)
        assert result == "a\nb\n    c"

    def test_prefix_and_line(self):
        doc = Prefix(2, Concat([Text("a"), Line(), Text("b")]))
        result = layout(doc)
        assert result == "  a\n  b"

    def test_union_picks_flat_if_fits(self):
        doc = Union(flat=Text("short"), broken=Concat([Text("long"), Line(), Text("text")]))
        assert layout(doc, max_width=80) == "short"

    def test_union_picks_broken_if_flat_too_long(self):
        doc = Union(flat=Text("this is too long"), broken=Text("ok"))
        assert layout(doc, max_width=5) == "ok"

    def test_max_width_boundary(self):
        """恰好等于 max_width 时 flat 能放下。"""
        doc = group(Concat([Text("abc"), Line(), Text("def")]))
        assert layout(doc, max_width=7) == "abc def"
        assert layout(doc, max_width=6) == "abc\ndef"

    def test_deeply_nested(self):
        doc = Nest(2, Nest(2, Concat([Text("a"), Line(), Text("b")])))
        result = layout(doc)
        assert result == "a\n    b"

    def test_flat_linebreak_removal(self):
        """LineBreak flat 时消失。"""
        doc = group(Concat([Text("a"), LineBreak(), Text("b")]))
        assert layout(doc) == "ab"


class TestFitsFixedWidthPath:
    """`_fits` 的**定宽累加**路径必须吃得下 `Text` 子项（回归 2026-09-26 实测缺陷）。

    事故：`_fits_fixed_len` 写的是 `len(d.s)`，而 `Text` 的字段是 `text`——它是
    重构 `3b9b113` 把原 `case Text(s): col += len(s)`（**位置捕获模式**，`s` 由模式
    绑定）机械抽成谓词时，把模式变量名当成了属性名。症状：`_fits` 一旦遇到含 `Text`
    的 `Concat` 就 `AttributeError`（`layout` 主路径走 `_flat_w` 缓存，很少直接问
    `_fits`，所以夹具与真实语料都没抓到——这条判据是补上那个缺口）。
    """

    def test_fixed_len_reads_text_field(self):
        """定宽取长：Text 按字段 `text` 计字，非定宽变体返回 None。"""
        assert _fits_fixed_len(Text("abc")) == 3
        assert _fits_fixed_len(Empty()) is None

    def test_fits_concat_with_text_children(self):
        """含 Text 的 Concat：能放下 / 放不下都要给结论，而不是抛异常。"""
        assert _fits(80, Concat([Text("hello")])) is True
        assert _fits(4, Concat([Text("hello")])) is False
        assert _fits(3, Concat([Text("ab"), Text("c")])) is True
        assert _fits(2, Concat([Text("ab"), Text("c")])) is False
