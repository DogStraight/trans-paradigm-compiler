"""tests/parser/test_attribute_binder.py — 属性绑定诊断与 Node 友好属性报错。

背景：rule_node 上的属性来自语法 TOML 的 node = { cond = "$3" } 位置捕获。
若 slot 匹配失败返回 None（或路径不存在），属性不挂载，下游访问抛裸
AttributeError。修复分三层：
    1. 静态 $N 越界 → GrammarRule 加载时 fail-fast（tests/core/test_rule_schema.py）
    2. slot 越界运行时防御 → bind_attributes 输出 WARN
    3. Node.__getattr__ 友好报错 + 路径提取失败 DEBUG 诊断（默认静默）
"""

import pytest

from core.define import Node, GrammarRule
from parser.attribute_binder import (
    _transfer_comment_slots,
    bind_attributes,
    extract_from_spec,
    get_attr_by_path,
)


class _Sink:
    """最小 Parser 替身：只提供 bind_attributes 需要的 _warn/_log_state。"""

    LOG_DEBUG = 0

    def __init__(self):
        self.warns = []
        self.logs = []

    def _warn(self, message, context=None):
        del context  # Parser 协议签名参数
        self.warns.append(message)

    def _log_state(self, action, mode="a", level=0, context=None):
        del mode, context  # Parser 协议签名参数
        self.logs.append((level, action))


class TestTransferCommentSlots:
    """内联展开时的注释槽迁移（`try_inline_rule` 调 `_transfer_comment_slots`）。

    背景：`inline = true` 的规则节点会被展开丢弃——挂它槽上的注释随节点消失
    （实测 `wire a = /* c */ b;` / `wire a = // why\n b;` 两处整条丢失）。
    """

    def test_list_slot_moved_and_deduped(self):
        """列表槽（leading/inline）整体迁移，逐条去重。"""
        src = Node("Init")
        src.add_attr("_comment_slots", {"inline": ["/* c */"], "leading": ["// l"]})
        dst = Node("Identifier", value="b")
        _transfer_comment_slots(src, dst)
        assert dst._comment_slots == {"inline": ["/* c */"], "leading": ["// l"]}

    def test_trailing_converted_to_leading(self):
        """trailing 转 leading（LineSuffix 停在替身节点末尾会排在父布局 `;` 前）。"""
        src = Node("Init")
        src.add_attr("_comment_slots", {"trailing": ["// why"]})
        dst = Node("Identifier", value="b")
        _transfer_comment_slots(src, dst)
        assert dst._comment_slots == {"leading": ["// why"]}

    def test_dict_slot_merged_with_dedup(self):
        """字典槽（inline_after = {锚: [(注释, 行)]}）逐锚合并，重复条目不双份。"""
        src = Node("Init")
        src.add_attr(
            "_comment_slots", {"inline_after": {"=": [("/* c */", 3), ("/* d */", 4)]}}
        )
        dst = Node("Identifier", value="b")
        dst.add_attr("_comment_slots", {"inline_after": {"=": [("/* c */", 3)]}})
        _transfer_comment_slots(src, dst)
        assert dst._comment_slots["inline_after"] == {"=": [("/* c */", 3), ("/* d */", 4)]}

    def test_scalar_slot_moved(self):
        """非列表/字典的槽值原样迁移（防御式分支）。"""
        src = Node("Init")
        src.add_attr("_comment_slots", {"note": "x"})
        dst = Node("Identifier", value="b")
        _transfer_comment_slots(src, dst)
        assert dst._comment_slots == {"note": "x"}

    def test_noop_without_source_slots_or_node(self):
        """无源槽 / 非 Node 目标（linter 原子占位）时不报错、不挂槽。"""
        dst = Node("Identifier", value="b")
        _transfer_comment_slots(None, dst)
        _transfer_comment_slots(Node("Init"), None)
        assert getattr(dst, "_comment_slots", None) is None


class TestExtractFromSpec:
    def test_out_of_range_slot_returns_none(self):
        assert extract_from_spec(_Sink(), "$5", [Node("a")]) is None

    def test_missing_path_returns_none(self):
        assert extract_from_spec(_Sink(), "$1.cond", [Node("x")]) is None

    def test_literal_value_passthrough(self):
        assert extract_from_spec(_Sink(), "hello", []) == "hello"

    def test_plain_slot_returns_node(self):
        n = Node("a")
        assert extract_from_spec(_Sink(), "$1", [n]) is n


class TestGetAttrByPath:
    def test_nested_and_missing(self):
        n = Node("a", value="hi")
        assert get_attr_by_path(n, "value") == "hi"
        assert get_attr_by_path(n, "missing") is None
        assert get_attr_by_path(None, "x") is None
        assert get_attr_by_path(n, "") is n


class TestBindDiagnostics:
    def test_slot_out_of_range_warns_and_skips(self):
        # 运行时匹配列表短于 production（匹配器缺陷场景）→ WARN 且不挂载
        sink = _Sink()
        rule = GrammarRule(
            "IfStmt",
            parser={"production": ["a", "@E", "b"], "node": {"cond": "$2"}},
        )
        node = Node("IfStmt")
        bind_attributes(sink, node, rule, [Node("a")])
        assert not hasattr(node, "cond")
        assert any("cond" in w and "$2" in w for w in sink.warns)

    def test_ok_binding_silent(self):
        sink = _Sink()
        rule = GrammarRule("R", parser={"production": ["a"], "node": {"v": "$1"}})
        node = Node("R")
        bind_attributes(sink, node, rule, [Node("a", value="x")])
        assert node.v.value == "x"
        assert not sink.warns

    def test_missing_path_silent_by_default(self):
        # choice 分支形态差异：slot 存在但路径属性缺失 → 设计语义，静默
        sink = _Sink()
        rule = GrammarRule(
            "R",
            parser={"production": ["@X|@Y"], "node": {"port_type": "$1.port_type"}},
        )
        node = Node("R")
        bind_attributes(sink, node, rule, [Node("Y")])
        assert not hasattr(node, "port_type")
        assert not sink.warns

    def test_empty_optional_not_bound(self):
        sink = _Sink()
        rule = GrammarRule("R", parser={"production": ["a", "@X?"], "node": {"x": "$2"}})
        node = Node("R")
        bind_attributes(sink, node, rule, [Node("a"), Node("optional")])
        assert not hasattr(node, "x")
        assert not sink.warns

    def test_list_spec_merges(self):
        sink = _Sink()
        rule = GrammarRule(
            "R",
            parser={"production": ["@X", "@Y"], "node": {"items": ["$1", "$2"]}},
        )
        node = Node("R")
        bind_attributes(sink, node, rule, [Node("X"), Node("Y")])
        assert len(node.items) == 2


class TestNodeFriendlyAttributeError:
    def test_missing_attr_message_points_to_binding(self):
        n = Node("IfStmt", cond=Node("x"))
        with pytest.raises(AttributeError) as exc_info:
            _ = n.cond2
        msg = str(exc_info.value)
        assert "cond2" in msg
        assert "cond" in msg  # 现有属性列表
        assert "node 绑定" in msg

    def test_hasattr_still_false(self):
        n = Node("IfStmt")
        assert not hasattr(n, "cond")

    def test_getattr_default_still_works(self):
        n = Node("IfStmt")
        assert getattr(n, "cond", "fallback") == "fallback"
