"""Doc IR 新原语测试（ADR-0006 阶段 2）：Align / Fill。

直接构造 Doc 树验证 layout() 布局行为，不依赖 TOML 原语层。
"""

from renderer.doc import (
    Align,
    Break,
    Concat,
    Fill,
    IfBreakPad,
    IfFlatPad,
    Line,
    Nest,
    Pad,
    Text,
    group,
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


class TestPad:
    """对齐 padding 三件套（Veryl Pad/IfBreakPad/IfFlatPad 语义）。

    对齐进 Doc IR：padding 是 Doc 一等公民，参与 fits/break 布局决策。
    """

    def test_pad_always_emits(self):
        """Pad 无条件输出，flat/broken 均保留。"""
        doc = Concat([Text("a"), Pad(3), Text("b")])
        assert layout(doc, 80) == "a   b"

    def test_pad_zero_is_empty(self):
        """Pad(0) 等价于 Empty。"""
        doc = Concat([Text("a"), Pad(0), Text("b")])
        assert layout(doc, 80) == "ab"

    def test_pad_participates_in_fits(self):
        """Pad 计入 fits：padding 使 group 超宽时强制断行。

        'aaaa' + Pad(3) + ':' = 8 字符；宽度 6 放不下 → broken。
        """
        doc = group(
            Nest(2, Concat([Text("aaaa"), Pad(3), Text(":"), Line(), Text("u32")]))
        )
        assert layout(doc, 8) == "aaaa   :\n  u32"

    def test_pad_in_fill_flat_width(self):
        """Pad 参与 _flat_width 计算（fill 的宽度预算）。"""
        doc = Fill([Concat([Text("aa"), Pad(2)]), Line(), Text("bb")])
        # 'aa  ' = 4 + ' bb' 放得下 → 单行
        assert layout(doc, 10) == "aa   bb"

    def test_if_break_pad_only_broken(self):
        """IfBreakPad 仅 broken 输出；flat 模式消失（0 计 fits）。"""
        flat = group(
            Nest(2, Concat([Text("a"), IfBreakPad(3), Text(":"), Line(), Text("u32")]))
        )
        # flat 放得下：padding 不输出
        assert layout(flat, 80) == "a: u32"

        broken = group(
            Nest(2, Concat([Text("aaaaaaaa"), IfBreakPad(3), Text(":"), Line(), Text("u32")]))
        )
        # 超宽断行：padding 输出
        assert layout(broken, 8) == "aaaaaaaa   :\n  u32"

    def test_if_break_pad_zero_width(self):
        """IfBreakPad(0) 等价于 Empty（flat/broken 均无输出）。"""
        doc = group(Nest(2, Concat([Text("aa"), IfBreakPad(0), Text(":"), Line(), Text("b")])))
        assert layout(doc, 4) == "aa:\n  b"

    def test_if_flat_pad_only_flat(self):
        """IfFlatPad 仅 flat 输出；broken 消失。"""
        doc = group(
            Nest(2, Concat([Text("aa"), IfFlatPad(2), Text(":"), Line(), Text("bb")]))
        )
        # flat：'aa  : bb' 放得下 → padding 输出
        assert layout(doc, 20) == "aa  : bb"

        broken = group(
            Nest(2, Concat([Text("aaaa"), IfFlatPad(6), Text(":"), Line(), Text("bb")]))
        )
        # broken：padding 消失
        assert layout(broken, 6) == "aaaa:\n  bb"

    def test_if_flat_pad_overflow_forces_break(self):
        """IfFlatPad 计入 fits：padding 超宽可强制 group 断行。

        'aaaa' + IfFlatPad(6) = 10 字符；宽度 8 放不下 → broken（padding 消失）。
        """
        doc = group(
            Nest(2, Concat([Text("aaaa"), IfFlatPad(6), Text(":"), Line(), Text("bb")]))
        )
        assert layout(doc, 8) == "aaaa:\n  bb"

    def test_pad_inside_fill_breaks(self):
        """Pad 在 fill 内容项内：折行后仍保留（对齐参与每行）。"""
        doc = Nest(4, Fill([Concat([Text("aa"), Pad(2)]), Line(), Text("bb")]))
        assert layout(doc, 4) == "aa  \n    bb"


class TestFitsContinuation:
    """fits 带外层 continuation（Veryl fits_flat 语义）。

    group 的 flat 判定要计入后续兄弟的宽度——防止"group 单独 fits、
    组合 continuation 溢出"（fill 模式邻居项组合行溢出的根因）。
    """

    def test_group_breaks_when_continuation_overflows(self):
        """group 自身 fits 但后续兄弟超宽 → group 选 broken。

        'aaaa bbb' 单独 8 字符 fits w10，但接 ' + XXXX' 后 16 字符超宽。
        """
        g = group(Nest(0, Concat([Text("aaaa"), Line(), Text("bbb")])))
        doc = Concat([g, Text(" + XXXX")])
        assert layout(doc, 10) == "aaaa\nbbb + XXXX"

    def test_group_stays_flat_when_continuation_fits(self):
        """continuation 放得下 → group 保持 flat。"""
        g = group(Nest(0, Concat([Text("aaaa"), Line(), Text("bbb")])))
        doc = Concat([g, Text(" + X")])
        assert layout(doc, 16) == "aaaa bbb + X"

    def test_group_fits_without_continuation(self):
        """无后续兄弟：group 判定只看自己（与旧行为一致）。"""
        g = group(Nest(0, Concat([Text("aaaa"), Line(), Text("bbb")])))
        assert layout(g, 10) == "aaaa bbb"

    def test_continuation_after_hardline_not_counted(self):
        """后续兄弟含硬换行 → 换行后是新行，不参与预算（到首个 break 为止）。"""
        g = group(Nest(0, Concat([Text("aa"), Line(), Text("bb")])))
        doc = Concat([g, Break(), Text("cccc")])
        # group 单独 fits → flat；Break 后 cccc 在新行
        assert layout(doc, 10) == "aa bb\ncccc"

    def test_nested_group_continuation(self):
        """嵌套 group：外层 continuation 计入内层判定。

        '[start] ' (8) + inner flat 'xx yy' (5) + ' [end]' (6) = 19 > w12
        → inner 感知 continuation 超宽 → broken。
        """
        inner = group(Nest(0, Concat([Text("xx"), Line(), Text("yy")])))
        outer = Concat([Text("[start] "), inner, Text(" [end]")])
        assert layout(outer, 12) == "[start] xx\nyy [end]"

    def test_nested_group_flat_when_roomy(self):
        """外层剩余宽度充足：inner 保持 flat。"""
        inner = group(Nest(0, Concat([Text("xx"), Line(), Text("yy")])))
        outer = Concat([Text("[start] "), inner, Text(" [end]")])
        assert layout(outer, 30) == "[start] xx yy [end]"

    def test_fill_item_with_continuation_breaks(self):
        """fill 内容项是 group：组合行溢出时该项 broken。"""
        item = group(Nest(0, Concat([Text("aaa"), Line(), Text("b")])))
        doc = Fill([item, Line(), Text("cccccccc")])
        # 第一项 flat 'aaa b' 5 + sep 1 + 'cccccccc' 8 = 14 > w8 → 该项 broken
        out = layout(doc, 8)
        lines = out.split("\n")
        assert lines[0] in ("aaa", "aaa b")
        assert "cccccccc" in lines[-1]
