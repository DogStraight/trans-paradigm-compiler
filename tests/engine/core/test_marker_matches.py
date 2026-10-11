"""tests/engine/core/test_marker_matches.py — 引擎通用面 `core.define.marker_matches`。

**为什么需要它（跨形态）**：`transform/normalizer.py` 会把 `keyword.*` / `symbol.*` /
`literal.*` 的 token 叶子抽成**字符串属性值**（并消除 `optional/repeat/seq` 包装）。同一份
`typedef int myint;` 因此有两条形态：

    · 直接 parse（未 normalize）：token 是**节点** ⇒ `StorageClass > keyword.typedef`
    · 生产管线（normalize 后）：token 变**父节点的字符串属性** ⇒ `StorageClass.base = "typedef"`

只按节点名判会在生产口径下恒不命中（C 包符号收集曾因此在管线里把 typedef 全收成 variable，
直到 raw 校验误报才暴露）。本文件把该判据的**三形态语义**与**安全反例**钉在引擎侧：
值扫描为何不会误命中（字面量保引号 / 注释不在声明子树内 / 关键字不作标识符）。
"""

import pytest

from core.define import Node, marker_matches
from transform.normalizer import normalize_ast

_C_PACK, _C_PLUGINS = "grammar/c", "grammar/c/plugins"


def _raw_decl() -> Node:
    """未 normalize 形态：token 是子节点。"""
    decl = Node("Declaration")
    storage = Node("StorageClass")
    storage.add_attr("sub_node", [Node("keyword.typedef")])
    decl.add_attr("specs", storage)
    return decl


def _normalized_decl() -> Node:
    """normalize 后形态：token 变成父节点的字符串属性值（实测形状）。"""
    decl = Node("Declaration")
    storage = Node("StorageClass")
    storage.add_attr("base", "typedef")
    decl.add_attr("specs", storage)
    return decl


class TestMarkerForms:
    def test_node_name_form_hits(self):
        """未 normalize：子树含同名节点即命中。"""
        assert marker_matches(_raw_decl(), "keyword.typedef") is True

    def test_scalar_value_form_hits(self):
        """normalize 后：子树含标量属性值 == 去前缀短名即命中。"""
        assert marker_matches(_normalized_decl(), "keyword.typedef") is True

    def test_non_token_marker_is_node_name_only(self):
        """非 token 前缀的 marker（语法结构名）不给"值扫描"开口子：`typedef` 不命中。"""
        assert marker_matches(_normalized_decl(), "typedef") is False
        assert marker_matches(_normalized_decl(), "Declaration") is True

    @pytest.mark.parametrize(
        ("marker", "expected"),
        [
            ("StorageClass.base=typedef", True),
            ("StorageClass.base=int", False),
            ({"node": "StorageClass", "attr": "base", "value": "typedef"}, True),
            ({"node": "SimpleType", "attr": "base", "value": "typedef"}, False),
        ],
    )
    def test_slot_forms(self, marker, expected):
        """钉槽位形式：`载体.属性=值` 与 dict 都只认该槽位。"""
        assert marker_matches(_normalized_decl(), marker) is expected


class TestSafety:
    """值扫描的安全反例（生产形态相关，逐条实测）。"""

    def test_node_name_is_not_a_scalar_value(self):
        """结构元数据不参与值扫描：节点名叫 `typedef` 不构成命中。"""
        assert marker_matches(Node("typedef"), "keyword.typedef") is False

    def test_literal_keeps_quotes_so_it_cannot_match_bare_short_name(self):
        """`literal.*` 抽取保留原文（含引号）⇒ 字符串字面量不会等于裸短名。

        两条断言合起来：`normalize_ast` 真的保留引号；因此声明子树里那个字符串
        `'"typedef"'` 与裸短名 `typedef` 不相等，不构成命中。
        """
        literal = Node("literal.string")
        literal.add_attr("value", '"typedef"')
        assert normalize_ast(literal) == '"typedef"'  # 引号保留（normalizer 约定）

        decl = Node("Declaration")
        decl.add_attr("init_value", '"typedef"')  # 归一后落在声明子树里的字面量字符串
        assert marker_matches(decl, "keyword.typedef") is False

    def test_real_ast_comment_and_literal_are_not_markers(self):
        """真实生产形态：注释/字面量里的 `typedef` 不落进任何 Declaration 子树。"""
        from core.config_registry import ConfigRegistry
        from core.define import GrammarRulesRegister, iter_nodes
        from lexer import Lexer
        from parser import setup_grammar
        from parser.parser_core import Parser
        from parser.rule_selector import RuleSelector

        ConfigRegistry.load_language(_C_PACK, plugins_dir=_C_PLUGINS)
        rules = setup_grammar(_C_PACK, GrammarRulesRegister(), ext_dirs=[_C_PLUGINS])
        stmt = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        parser = Parser(
            rules_dir=_C_PACK,
            rules=rules,
            rule_selector=RuleSelector(rules, stmt),
            log_file="",
        )
        lexer = Lexer(rules_dir=_C_PACK, ext_dirs=[_C_PLUGINS])

        def decls(src: str) -> list[Node]:
            ast = parser.parse(lexer.tokenize(src))
            assert ast is not None, src
            norm = normalize_ast(ast)
            return [n for n in iter_nodes(norm) if n.node_name == "Declaration"]

        # 反例：注释与字符串字面量里出现 typedef，均不得被当标记
        for src in (
            "int guarded; /* typedef */\n",
            "int guarded; // typedef\n",
            "/* typedef */\nint guarded;\n",
            'char *s = "typedef";\n',
        ):
            hits = [marker_matches(d, "keyword.typedef") for d in decls(src)]
            assert hits and not any(hits), (src, hits)

        # 正例对照：真 typedef 声明必须命中（否则反例是"永远不命中"的假安全）
        assert any(marker_matches(d, "keyword.typedef") for d in decls("typedef int myint;\n"))

    def test_keyword_cannot_be_an_identifier(self):
        """关键字不可能作标识符：词法层 `typedef` 是 keyword token，标识符是 `id`。

        这条是"值扫描"安全的前提之一——`Identifier.content` 永远不会等于关键字短名，
        故值命中只可能来自真正的 token 叶子槽位。
        """
        from core.config_registry import ConfigRegistry
        from lexer import Lexer

        ConfigRegistry.load_language(_C_PACK, plugins_dir=_C_PLUGINS)
        lexer = Lexer(rules_dir=_C_PACK, ext_dirs=[_C_PLUGINS])
        tokens = lexer.tokenize("typedef typedefx;\n")
        assert tokens[0].type.startswith("keyword.") and tokens[0].content == "typedef"
        assert tokens[1].type == "id" and tokens[1].content == "typedefx"
