"""render_node 的 body_cfg["indent"] 缩进控制测试。

验证三态：未声明/true = 1 级缩进、false = 不缩进、int = N 级。
防止该字段退回"死配置"（曾存在：body 缩进恒为 1 级、字段从不被读取）。

不加载 TOML，直接构造 Node + layout dict，走 render_node。
"""

from core.define import Node
from renderer.doc import layout
from renderer.node_renderer import render_node


def _make_fake_renderer():
    """最小 fake renderer：只提供 render_node 依赖的委托方法。"""

    class FakeRenderer:
        _INDENT_STR = "    "
        _children_field = "sub_node"

        def _indent(self, level):
            return level * len(self._INDENT_STR)

        def _get_merged_layout(self, parent_layout, child_name):
            del parent_layout, child_name  # renderer 协议签名参数
            return {"layout": {"ref": "value"}}

        def _eval(self, expr, node, parent_layout=None):
            from renderer.primitives import eval_expr

            return eval_expr(expr, node, parent_layout, self)

    return FakeRenderer()


def _render_body_cfg(body_cfg):
    """Block{sub_node: [x, y]} 在 body_cfg 下的渲染行列表。"""
    x = Node("Item", value="x")
    y = Node("Item", value="y")
    node = Node("Block", sub_node=[x, y])
    fake = _make_fake_renderer()
    doc = render_node(node, {"body": body_cfg}, fake)
    return layout(doc).splitlines()


class TestBodyIndent:
    def test_unset_indents_one_level(self):
        """未声明 indent → 默认缩进 1 级（兼容既有行为）。"""
        lines = _render_body_cfg({"source": "sub_node"})
        assert lines[1] == "    x"
        assert lines[2] == "    y"

    def test_true_indents_one_level(self):
        lines = _render_body_cfg({"indent": True})
        assert lines[1] == "    x"
        assert lines[2] == "    y"

    def test_false_no_indent(self):
        lines = _render_body_cfg({"indent": False})
        assert lines[1] == "x"
        assert lines[2] == "y"

    def test_int_levels(self):
        lines = _render_body_cfg({"indent": 2})
        assert lines[1] == "        x"
        assert lines[2] == "        y"

    def test_false_keeps_item_separation(self):
        """indent=false 只去缩进，body 项仍逐行分隔。"""
        lines = _render_body_cfg({"indent": False})
        assert len(lines) == 3  # 首空行 + 两项各一行
        assert lines[1] == "x"
        assert lines[2] == "y"
