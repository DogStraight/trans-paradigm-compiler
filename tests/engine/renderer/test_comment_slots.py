"""节点注释槽位消费端测试（P1.5 注释节点模型步骤 1）。

节点属性 _comment_slots: {槽位名: [注释文本]}：
  leading  — 节点文本前独立行（`// 前置注释` 在语句上方）
  trailing — 节点后行尾锚定（LineSuffix 渲染行尾注释）

不加载 TOML，直接构造 Node + layout dict，走 render_node。
"""

from core.define import Node
from renderer.doc import layout
from renderer.node_renderer import render_node

from test_renderer_body_indent import _make_fake_renderer


def _render(node, layout_cfg):
    doc = render_node(node, layout_cfg, _make_fake_renderer())
    return layout(doc)


def _stmt(text: str) -> Node:
    return Node("Stmt", value=text)


class TestLeadingSlot:
    def test_leading_comment_before_node(self):
        """leading 槽位：注释在节点文本前独立行。"""
        node = _stmt("x")
        node.add_attr("_comment_slots", {"leading": ["// 前置注释"]})
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "// 前置注释\nx"

    def test_multiple_leading_comments(self):
        """多个 leading 注释各占一行。"""
        node = _stmt("x")
        node.add_attr(
            "_comment_slots", {"leading": ["// 注释一", "/* 注释二 */"]}
        )
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "// 注释一\n/* 注释二 */\nx"


class TestLeadingOwnLineSlot:
    def test_own_line_comment_takes_its_own_line(self):
        """leading_own_line：行终止型注释硬换行独占成行（前后各一硬换行）。"""
        node = _stmt("x")
        node.add_attr(
            "_comment_slots", {"leading_own_line": ["// 独占行"]}
        )
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "\n// 独占行\nx", repr(out)

    def test_multiple_own_line_comments_no_blank_line(self):
        """多条独占行注释之间不叠空行（块首尾各一硬换行，行间单换行）。"""
        node = _stmt("x")
        node.add_attr(
            "_comment_slots", {"leading_own_line": ["// 一", "// 二"]}
        )
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "\n// 一\n// 二\nx", repr(out)

    def test_block_comment_in_own_line_slot_keeps_flow(self):
        """块注释（非行终止型）不走硬换行（不断源片段）。"""
        node = _stmt("x")
        node.add_attr(
            "_comment_slots", {"leading_own_line": ["/* 块 */"]}
        )
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "/* 块 */\nx", repr(out)


class TestVerbatimNodeSlots:
    def test_verbatim_node_still_emits_leading_slot(self):
        """直出文本节点（`_verbatim_text`，宏调用类）也要输出前置槽。

        直出路径不走布局，但附着注释在节点 span 之外——漏输出会让注释
        （含 tpc marker，其文本承载条件块原文）静默丢失。
        """
        node = _stmt("x")
        node.add_attr("_verbatim_text", "`M(c)")
        node.add_attr("_comment_slots", {"leading_own_line": ["// <tpc:cond:1>"]})
        out = _render(node, {"layout": {"ref": "value"}})
        assert "`M(c)" in out and "// <tpc:cond:1>" in out, repr(out)


class TestTrailingSlot:
    def test_trailing_comment_line_end(self):
        """trailing 槽位：行尾注释锚定语句行尾。"""
        node = _stmt("x")
        node.add_attr("_comment_slots", {"trailing": ["// 行尾注释"]})
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "x // 行尾注释"

    def test_both_slots(self):
        """leading + trailing 同时存在：前置独立行 + 行尾锚定。"""
        node = _stmt("x")
        node.add_attr(
            "_comment_slots",
            {"leading": ["// 前置"], "trailing": ["// 行尾"]},
        )
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "// 前置\nx // 行尾"


class TestInlineSlot:
    def test_inline_comment_same_line_before_node(self):
        """inline 槽位：注释在节点文本前同行（行中注释）。"""
        node = _stmt("rst_n")
        node.add_attr("_comment_slots", {"inline": ["/* 嵌入注释 */"]})
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "/* 嵌入注释 */ rst_n"

    def test_inline_in_assign_expr(self):
        """`assign b = /* c */ rst_n;`：inline 注释在 = 后、RHS 前。"""
        from renderer.doc import Concat, Text

        rhs = _stmt("rst_n")
        rhs.add_attr("_comment_slots", {"inline": ["/* 嵌入注释 */"]})
        rhs_doc = render_node(rhs, {"layout": {"ref": "value"}}, _make_fake_renderer())
        doc = Concat([Text("assign b = "), rhs_doc])
        assert layout(doc) == "assign b = /* 嵌入注释 */ rst_n"

    def test_inline_plus_trailing(self):
        """inline + trailing 同时存在：前置同行 + 行尾锚定。"""
        node = _stmt("rst_n")
        node.add_attr(
            "_comment_slots",
            {"inline": ["/* 前置 */"], "trailing": ["// 行尾"]},
        )
        out = _render(node, {"layout": {"ref": "value"}})
        assert out == "/* 前置 */ rst_n // 行尾"


class TestSlotInBody:
    def test_leading_in_body_indented(self):
        """body 内子节点的 leading 注释继承缩进。"""
        a = _stmt("a")
        a.add_attr("_comment_slots", {"leading": ["// a 的注释"]})
        b = _stmt("b")
        node = Node("Block", sub_node=[a, b])
        out = _render(node, {"body": {"source": "sub_node"}})
        lines = out.splitlines()
        # 结构：空行 + 缩进的子节点（首行由 Break 产生）
        assert "    // a 的注释" in lines
        assert "    a" in lines
        assert "    b" in lines
