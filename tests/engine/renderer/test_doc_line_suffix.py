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
    Union,
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
        """group flat 模式（行终止注释，#72）：不得就地并入后续 token——落点升硬换行。"""
        from renderer.doc import group

        doc = group(
            Concat([Text("a"), LineSuffix(" // note"), Line(), Text("b")])
        )
        assert layout(doc, 80) == "a // note\nb"

    def test_block_comment_stays_inline_in_flat_group(self):
        """group flat 模式（块注释 line_ending=False）：不结束行，仍就地显示。"""
        from renderer.doc import group

        doc = group(
            Concat(
                [
                    Text("a"),
                    LineSuffix(" /* c */", line_ending=False),
                    Line(),
                    Text("b"),
                ]
            )
        )
        assert layout(doc, 80) == "a /* c */ b"

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


class TestLineSuffixUnion:
    """Union 两支挂起后缀不一致：行终止注释**不得就地落地**。

    背景（2026-10-19 修，历史见 CHANGELOG）：`_resolve_suffix_union` 曾对两支 pending
    不同的情形"各自就地落地"——把行终止注释写成 branch 末尾的 Text，父级同行后续
    token（`;`/`,`）印在注释之后 ⇒ 二遍渲染时被并进注释、产物非法。`pending` 只可能
    来自 `line_ending=True`（块注释在 `_suffix_entry` 就地落地），故"pending 非空 ⇒
    行终止型"是构造保证，引擎无需识别注释标点。

    修法（2026-10-19）：两支不一致时不再就地落地，强制 broken 支并把其挂起继续
    上提，由父层在下一个换行点前落地——行终止注释必须终结所在行。

    两支 pending 不同的来源：同一条注释在一支里被内部换行点冲刷（已落地、pending
    为空），在另一支里仍挂起在末尾。生产形态里 flat 是 broken 的 `flatten` 副本、
    同一 suffix 两支都有 ⇒ 差异只是**落地位置**，故选 broken 支不丢注释；手工构造
    "两支各带独有文本"的 Union 会丢 flat 独有文本（非生产形态，下方用例锁 broken
    侧语义）。
    """

    def test_mismatch_forces_broken_branch(self):
        """flat 支仍挂起、broken 支已被内部换行点冲刷 → 走 broken，`;` 不落进注释。"""
        flat = Concat([Text("a"), LineSuffix(" // note")])
        broken = Concat([Text("a"), LineSuffix(" // note"), Break()])
        assert layout(Concat([Union(flat, broken), Text(";")])) == "a // note\n;"

    def test_mismatch_propagates_broken_pending(self):
        """broken 支仍挂起、flat 支已冲刷 → 挂起上提到父级行尾（`a; // note`）。"""
        flat = Concat([Text("a"), LineSuffix(" // note"), Break()])
        broken = Concat([Text("a"), LineSuffix(" // note")])
        assert layout(Concat([Union(flat, broken), Text(";")])) == "a; // note"

    def test_both_branches_pending_keeps_broken_texts(self):
        """两支都非空且不同（nested insert 形态）：走 broken，两份文本各出现一次。"""
        flat = Concat([Text("a"), LineSuffix(" // extra")])
        broken = Concat([Text("a"), LineSuffix(" // n"), LineSuffix(" // extra")])
        out = layout(Concat([Union(flat, broken), Text(";")]))
        assert out == "a; // n // extra"
