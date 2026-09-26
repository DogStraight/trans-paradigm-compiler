"""Renderer 原语行为测试 — 直接调用 eval_expr + 最小 fake renderer。

不加载任何 TOML 布局文件，不依赖解析器。
手动构造 Node + 布局 expr dict，验证渲染原语输出。
"""

import pytest

from core.define import Node
from core.errors import ConfigError
from renderer.doc import layout
from renderer.primitives import eval_expr
from renderer.doc import Text

pytestmark = pytest.mark.smoke  # smoke：renderer 组代表（渲染原语，fake renderer 纯内存）


def _make_fake_renderer():
    """创建最小 fake renderer，供原语回调使用。"""

    class FakeRenderer:
        _INDENT_STR = "    "
        _layouts = {}

        def _indent(self, level):
            return level * len(self._INDENT_STR)

        def _render_inline(self, child_node, layout_cfg):
            del layout_cfg  # fake renderer 桩方法，不消费布局配置
            val = getattr(child_node, "value", None)
            if val is not None:
                return Text(str(val))
            return Text(child_node.node_name)

        def _get_merged_layout(self, parent_layout, child_name):
            del parent_layout, child_name  # fake renderer 桩方法
            return {}

        def _resolve_items(self, node, items_spec):
            if isinstance(items_spec, str):
                return getattr(node, items_spec, [])
            return []

        def _eval(self, expr, node, parent_layout=None):
            return eval_expr(expr, node, parent_layout, self)

    return FakeRenderer()


def _render_expr(expr, node):
    r = _make_fake_renderer()
    doc = eval_expr(expr, node, parent_layout=None, renderer=r)
    if doc is None:
        return ""
    return layout(doc)


def _n(node_name, **kw):
    return Node(node_name, **kw)


# ═══════════════════════════════════════════════════════
# suffix_when 原语
# ═══════════════════════════════════════════════════════

class TestSuffixWhenPrimitive:
    def test_condition_hit_appends_suffix(self):
        node = _n("Identifier", content=r"\$_BUF_")
        expr = {"suffix_when": {"startswith": "\\"}, "attr": "content", "text": " "}
        assert _render_expr(expr, node) == " "

    def test_condition_miss_returns_empty(self):
        node = _n("Identifier", content="plain_name")
        expr = {"suffix_when": {"startswith": "\\"}, "attr": "content", "text": " "}
        assert _render_expr(expr, node) == ""

    def test_custom_text(self):
        node = _n("Identifier", content=r"\esc")
        expr = {"suffix_when": {"startswith": "\\"}, "text": "; "}
        assert _render_expr(expr, node) == "; "

    def test_default_attr_is_content(self):
        node = _n("Identifier", content=r"\esc")
        expr = {"suffix_when": {"startswith": "\\"}}
        assert _render_expr(expr, node) == " "

    def test_non_string_attr_returns_empty(self):
        node = _n("Identifier", content=42)
        expr = {"suffix_when": {"startswith": "\\"}}
        assert _render_expr(expr, node) == ""

    def test_missing_attr_returns_empty(self):
        node = _n("Identifier")
        expr = {"suffix_when": {"startswith": "\\"}}
        assert _render_expr(expr, node) == ""


# ═══════════════════════════════════════════════════════
# text 原语
# ═══════════════════════════════════════════════════════

class TestTextPrimitive:
    def test_str_expr_returns_text(self):
        r = _make_fake_renderer()
        doc = eval_expr("hello", _n("x"), None, r)
        assert isinstance(doc, Text)
        assert doc.text == "hello"

    def test_str_expr_renders(self):
        assert _render_expr("world", _n("x")) == "world"

    def test_non_dict_non_str_fallback(self):
        r = _make_fake_renderer()
        doc = eval_expr(42, _n("x"), None, r)
        assert isinstance(doc, Text)
        assert doc.text == "42"


# ═══════════════════════════════════════════════════════
# ref 原语
# ═══════════════════════════════════════════════════════

class TestRefPrimitive:
    def test_ref_value_attr(self):
        node = _n("Keyword", value="wire")
        assert _render_expr({"ref": "value"}, node) == "wire"

    def test_ref_missing_attr(self):
        node = _n("Keyword")
        assert _render_expr({"ref": "nonexistent"}, node) == ""

    def test_ref_with_child_node(self):
        child = _n("Ident", value="x")
        parent = _n("Decl", name=child)
        assert _render_expr({"ref": "name"}, parent) == "x"


# ═══════════════════════════════════════════════════════
# line 原语
# ═══════════════════════════════════════════════════════

class TestLinePrimitive:
    def test_line_concat(self):
        node = _n("Pair", a=_n("id", value="x"), b=_n("id", value="y"))
        expr = {"line": [{"ref": "a"}, {"ref": "b"}]}
        assert _render_expr(expr, node) == "xy"

    def test_line_with_soft_break(self):
        node = _n("Pair", a=_n("id", value="hello"), b=_n("id", value="world"))
        expr = {"line": [{"ref": "a"}, {"soft": True}, {"ref": "b"}]}
        assert _render_expr(expr, node) == "hello world"

    def test_line_with_text_mixed(self):
        node = _n("Keyword", value="wire")
        expr = {"line": [{"ref": "value"}, " ;"]}
        assert _render_expr(expr, node) == "wire ;"

    def test_line_single_item(self):
        node = _n("id", value="just_me")
        assert _render_expr({"line": [{"ref": "value"}]}, node) == "just_me"


# ═══════════════════════════════════════════════════════
# join 原语
# ═══════════════════════════════════════════════════════

class TestJoinPrimitive:
    def test_join_two_items(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("List", items=[a, b])
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == "a, b"

    def test_join_single_item(self):
        a = _n("id", value="only")
        node = _n("List", items=[a])
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == "only"

    def test_join_empty(self):
        node = _n("List", items=[])
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == ""


def _cmt(text):
    """构造独占行注释节点（_comment 引擎标记，ADR-0013 阶段 B）。"""
    c = _n("Comment", value=text)
    c.add_attr("_comment", True)
    return c


class TestJoinCommentItem:
    """独占行注释混入 join items 独立行渲染（ADR-0013 阶段 B2）。

    _comment 引擎标记（parser collect_line_comments 挂）——注释是列表
    项间分隔，不参与 join 分隔符：注释前项尾随分隔符归属其行尾、
    注释独立行（前后换行）、注释后项为新段首（无分隔符）。
    """

    def test_comment_mid_breaks_list(self):
        a = _n("id", value="input a")
        c = _cmt("// Look-Ahead Interface")
        b = _n("id", value="output b")
        node = _n("List", items=[a, c, b])
        expr = {"join": ", ", "items": "items", "first_soft": True, "nest": 1}
        out = _render_expr(expr, node)
        assert out == " input a,\n    // Look-Ahead Interface\n    output b"

    def test_comment_at_tail_no_trailing_blank(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        c = _cmt("// tail")
        node = _n("List", items=[a, b, c])
        expr = {"join": ", ", "items": "items", "first_soft": True, "nest": 1}
        out = _render_expr(expr, node)
        assert out == " a, b,\n    // tail"
        assert not out.endswith("\n\n")

    def test_comment_at_head(self):
        c = _cmt("// head")
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("List", items=[c, a, b])
        expr = {"join": ", ", "items": "items", "first_soft": True, "nest": 1}
        # 首项即注释段（容器首元素前独占注释）：独占行语义——注释前硬
        # Break（first_soft 空格会把注释贴到父上下文行尾，如
        # `module m( // head`），注释独立行 + nest 缩进。
        out = _render_expr(expr, node)
        assert out == "\n    // head\n    a, b"

    def test_consecutive_comments_each_line(self):
        c1 = _cmt("// c1")
        c2 = _cmt("// c2")
        a = _n("id", value="a")
        node = _n("List", items=[c1, c2, a])
        expr = {"join": ", ", "items": "items", "first_soft": True, "nest": 1}
        out = _render_expr(expr, node)
        assert out == "\n    // c1\n    // c2\n    a"

    def test_no_comment_regression(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("List", items=[a, b])
        expr = {"join": ", ", "items": "items", "first_soft": True, "nest": 1}
        assert _render_expr(expr, node) == " a, b"

    def test_comment_item_alone(self):
        c = _cmt("// only")
        node = _n("List", items=[c])
        expr = {"join": ", ", "items": "items", "first_soft": True, "nest": 1}
        assert _render_expr(expr, node) == "\n    // only"


class TestJoinCommentPlacementRegressions:
    """注释落位三处缺陷的回归门（2026-09-25 实测成因，逐条可判死）。

    三条都在 C 包保真度闭环上暴露（渲染不幂等 / 注释静默丢失 / 输出非法 C），
    但成因都在引擎 `join`，故门设在本层（不依赖语言包与解析器）。
    """

    def test_sep_inline_comment_single_space(self):
        """分隔符后的行中注释：注释前后各**一个**空格（缺陷：注释后又补一个
        空格，与紧随的 SoftLine 叠加成双空格——`int a, /* mid */  b;`，二次
        渲染逐字不同 ⇒ 不幂等；broken 形态下那个空格还成了行尾空白）。
        """
        a, b = _n("id", value="a"), _n("id", value="b")
        node = _n("List", items=[a, b])
        node.add_attr("_comment_slots", {"inline_after": {",": [("/* mid */", 1)]}})
        expr = {"join": ", ", "items": "items"}
        assert _render_expr(expr, node) == "a, /* mid */ b"

    def test_comment_head_of_hard_concat_list_takes_own_line(self):
        """硬拼列表（`join=""`，如声明符后缀链）首项即注释：必须补 Break。

        缺陷：`_asm_comment_item` 只在"行内分隔"下补首 Break，把硬拼与换行分隔
        混为一谈——注释**粘在**前一片段之后，`//` 注释随即吞掉后续代码（实测
        `int f(\\n// c\\nint a);` → `int f// c` + 换行 + `(int a);`，二次渲染整段
        被吃进注释 ⇒ 输出非法 C）。
        """
        c, a = _cmt("// head"), _n("id", value="(int a)")
        node = _n("List", items=[c, a])
        expr = {"join": "", "items": "items"}
        assert _render_expr(expr, node) == "\n// head\n(int a)"

    def test_head_comment_on_nested_node_hoisted(self):
        """首注释挂在项内**更深**节点上时也要取到（缺陷：只认项自身 sub_node 首位
        → 注释静默丢弃）。

        成因：容器首元素前的独占行注释由 `_claim_head_comments` 领，而领到的是
        行首那条规则的**最内层**节点——列表项本身以标识符开头时（`Enumerator`
        → `Identifier`、`InitDeclarator` → … → `Identifier`），注释挂在项内更深
        处（实测 `enum e { // c\\n A }` 整条注释消失）。
        """
        c = _cmt("// head")
        inner = _n("Id", value="A", sub_node=[c])  # 注释在项首脊线尽头
        item = _n("Enum", name=inner)  # 项自身 sub_node 为空，子节点在绑定属性上
        node = _n("List", items=[item])
        expr = {"join": ", ", "items": "items"}
        out = _render_expr(expr, node)
        assert out == "\n// head\nEnum", out
        assert not inner.sub_node, "注释应已从内层节点摘除（否则会二次渲染）"


# ═══════════════════════════════════════════════════════
# when 原语（属性分发布局）
# ═══════════════════════════════════════════════════════


def _when_expr(cond, then=None, else_=None):
    e = {"when": cond}
    if then is not None:
        e["then"] = then
    if else_ is not None:
        e["else"] = else_
    return e


class TestWhenPrimitive:
    """`when`：按节点属性值选支布局（同节点名多形态的文本分发）。

    首个消费方是 C 包的 pratt `UnaryOp`（`position` 分前缀/后缀，`-x` 对 `i++`）。
    """

    def test_eq_hit_takes_then(self):
        node = _n("UnaryOp", op="++", position="postfix")
        expr = _when_expr({"attr": "position", "eq": "postfix"}, {"ref": "op"}, {"ref": "miss"})
        assert _render_expr(expr, node) == "++"

    def test_eq_miss_takes_else(self):
        node = _n("UnaryOp", op="-", position="prefix")
        expr = _when_expr({"attr": "position", "eq": "postfix"}, {"ref": "miss"}, {"ref": "op"})
        assert _render_expr(expr, node) == "-"

    def test_branch_may_be_omitted(self):
        """缺 `else` = 该分支不输出（不是错）。"""
        node = _n("UnaryOp", op="-", position="prefix")
        expr = _when_expr({"attr": "position", "eq": "postfix"}, {"ref": "op"})
        assert _render_expr(expr, node) == ""

    def test_in_and_exists_and_startswith(self):
        node = _n("N", kind="c", content="\\x")
        assert _render_expr(_when_expr({"attr": "kind", "in": ["a", "c"]}, {"ref": "kind"}), node) == "c"
        assert _render_expr(_when_expr({"attr": "nope", "exists": False}, {"ref": "kind"}), node) == "c"
        assert _render_expr(_when_expr({"attr": "content", "startswith": "\\"}, {"ref": "kind"}), node) == "c"
        # 属性缺失：除 exists 外一律不命中
        assert _render_expr(_when_expr({"attr": "nope", "eq": "x"}, {"ref": "kind"}), node) == ""

    @pytest.mark.parametrize(
        "cond",
        [
            "not-a-dict",
            {"eq": "x"},                       # 缺 attr
            {"attr": "position"},              # 无条件键
            {"attr": "position", "eq": "a", "in": ["b"]},   # 两个条件键
        ],
    )
    def test_malformed_condition_fails_fast(self, cond):
        """声明形态非法即报错——**不许**静默输出空串（同"缺布局静默丢内容"根因）。"""
        node = _n("UnaryOp", op="-", position="prefix")
        with pytest.raises(ConfigError):
            _render_expr(_when_expr(cond, {"ref": "op"}), node)


class TestUnknownPrimitiveKeyFailsFast:
    """认不出的布局键**报错**，不静默输出空串（"缺布局静默丢内容"的根因）。

    实测症状来源：规则漏布局 / 键拼错时 `eval_expr` 返回 None，渲染端把整块
    内容当"无内容"跳过（本包最早的症状是 70 条规则只有 1 条有布局、渲染为空串）。
    """

    def test_misspelled_key_raises(self):
        node = _n("id", value="x")
        with pytest.raises(ConfigError, match="已知原语"):
            _render_expr({"lin": [{"ref": "value"}]}, node)  # `line` 拼错

    def test_missing_primitive_raises(self):
        with pytest.raises(ConfigError):
            _render_expr({"items": ["a"]}, _n("List"))

    def test_element_options_beside_dispatch_key_still_ok(self):
        """元素键（items/nest/first_soft…）与分发键同层是正常形态，不是"认不出"。"""
        node = _n("List", items=[_n("id", value="a")])
        expr = {"join": ", ", "items": "items", "first_soft": False, "nest": 0}
        assert _render_expr(expr, node) == "a"


# ═══════════════════════════════════════════════════════
# group 原语
# ═══════════════════════════════════════════════════════
class TestGroupPrimitive:
    def test_group_flat(self):
        node = _n("id", value="short")
        expr = {"group": [{"ref": "value"}]}
        assert _render_expr(expr, node) == "short"

    def test_group_with_line(self):
        node = _n("Pair", a=_n("id", value="a"), b=_n("id", value="b"))
        expr = {"group": [{"line": [{"ref": "a"}, {"soft": True}, {"ref": "b"}]}]}
        assert _render_expr(expr, node) == "a b"


# ═══════════════════════════════════════════════════════
# opt 原语
# ═══════════════════════════════════════════════════════

class TestOptPrimitive:
    def test_opt_present(self):
        node = _n("Labelled", label=_n("Keyword", value="LABEL:"))
        expr = {"opt": {"ref": "label"}}
        assert _render_expr(expr, node) == "LABEL:"

    def test_opt_absent(self):
        node = _n("Labelled")
        expr = {"opt": {"ref": "label"}}
        assert _render_expr(expr, node) == ""


# ═══════════════════════════════════════════════════════
# 组合
# ═══════════════════════════════════════════════════════

class TestCombined:
    def test_line_with_opt(self):
        node = _n("Labelled",
                   label=_n("Keyword", value="tag:"),
                   value=_n("id", value="data"))
        expr = {"line": [
            {"opt": {"ref": "label"}},
            " ",
            {"ref": "value"},
        ]}
        assert _render_expr(expr, node) == "tag: data"

    def test_join_in_line(self):
        a = _n("id", value="a")
        b = _n("id", value="b")
        node = _n("Container", items=[a, b], name=_n("id", value="result"))
        expr = {"line": [
            {"ref": "name"},
            " = ",
            {"join": ", ", "items": "items"},
        ]}
        assert _render_expr(expr, node) == "result = a, b"
