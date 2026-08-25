"""Doc IR 新原语测试（ADR-0006 阶段 2）：Align / Fill。

直接构造 Doc 树验证 layout() 布局行为，不依赖 TOML 原语层。
"""

from renderer.doc import (
    Align,
    Break,
    Concat,
    Fill,
    Line,
    Nest,
    Text,
    layout,
)


class TestAlign:
    def test_align_first_line_untouched(self):
        """首行从当前列渲染，不受 Align 影响。"""
        doc = Concat([Text("a"), Align(8, Concat([Line(), Text("b")]))])
        assert layout(doc) == "a\n        b"

    def test_align_sets_absolute_column(self):
        """换行缩进列 = 对齐列（绝对），不是相对偏移。"""
        doc = Concat([Text("xx"), Align(4, Concat([Line(), Text("y")]))])
        assert layout(doc) == "xx\n    y"

    def test_align_with_nest_inside(self):
        """Align 内部嵌套 Nest：相对对齐列再偏移。"""
        doc = Concat(
            [Text("a"), Align(4, Concat([Nest(2, Concat([Line(), Text("b")]))]))]
        )
        assert layout(doc) == "a\n      b"

    def test_align_max_with_current_indent(self):
        """对齐列小于当前缩进时取 max（不缩回）。

        Nest 语义：首行不带缩进（Prefix 才是首行缩进），故首行 'a' 顶格；
        换行缩进列 = max(Nest 6, Align 2) = 6。
        """
        doc = Nest(6, Concat([Text("a"), Align(2, Concat([Line(), Text("b")]))]))
        assert layout(doc) == "a\n      b"


class TestFill:
    def test_fill_all_fits_one_line(self):
        """全部放得下 → 分隔符呈空格，单行。"""
        doc = Fill([Text("a"), Line(), Text("b"), Line(), Text("c")])
        assert layout(doc, 40) == "a b c"

    def test_fill_breaks_when_overflow(self):
        """放不下 → 在分隔符处换行（贪心逐元素）。"""
        doc = Fill([Text("aaaa"), Line(), Text("bbbb"), Line(), Text("cccc")])
        out = layout(doc, 10)
        lines = out.split("\n")
        # 宽度 10：'aaaa bbbb' = 9 放得下，'cccc' 换行
        assert lines == ["aaaa bbbb", "cccc"]

    def test_fill_multiple_breaks(self):
        """长序列产生多个折行点（中间态：非全 flat 非全 broken）。"""
        doc = Fill(
            [Text("aa"), Line(), Text("bb"), Line(), Text("cc"), Line(), Text("dd")]
        )
        out = layout(doc, 6)
        lines = out.split("\n")
        assert lines == ["aa bb", "cc dd"]

    def test_fill_break_then_fit_again(self):
        """折行后剩余项可再次同行（贪心恢复）。"""
        doc = Fill(
            [
                Text("aaa"),
                Line(),
                Text("bbb"),
                Line(),
                Text("c"),
                Line(),
                Text("d"),
            ]
        )
        out = layout(doc, 7)
        lines = out.split("\n")
        assert lines == ["aaa bbb", "c d"]

    def test_fill_single_item(self):
        doc = Fill([Text("only")])
        assert layout(doc) == "only"

    def test_fill_nested_indent(self):
        """Fill 在 Nest 内：换行缩进 = Nest 缩进列（首行不带缩进，Nest 语义）。"""
        doc = Nest(4, Fill([Text("aa"), Line(), Text("bb")]))
        assert layout(doc, 5) == "aa\n    bb"

    def test_fill_hard_break_sep(self):
        """分隔符用 Break（硬换行）：始终换行，不受宽度影响。"""
        doc = Fill([Text("a"), Break(), Text("b")])
        assert layout(doc, 80) == "a\nb"
