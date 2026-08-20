"""tests/parser/test_production_serialize.py — production 还原序列化器。

serialize_production_tree 与 analyze_production_features 对称：feature 树 →
production 字符串，用于 EXT inject 的结构化合并（替代字符串正则）。
覆盖：
    - 各形态序列化（token/call/choice/seq/repeat/optional/plus）
    - round-trip 语义等价（analyze → serialize → analyze 树相等）
    - 真实语法全量 production round-trip
"""

import pytest

from parser.rule_selector import (
    analyze_production_features,
    serialize_production_tree,
)


def _roundtrip(prod: str) -> bool:
    t1 = analyze_production_features(prod)
    if t1 is None:
        return True
    s = serialize_production_tree(t1)
    t2 = analyze_production_features(s)
    return t1 == t2


class TestSerializeShapes:
    def test_token(self):
        assert serialize_production_tree(analyze_production_features("keyword.case")) == "keyword.case"

    def test_call(self):
        assert serialize_production_tree(analyze_production_features("@Expression")) == "@Expression"

    def test_choice(self):
        assert serialize_production_tree(analyze_production_features("@A|@B")) == "@A|@B"

    def test_choice_with_composite_member_parenthesized(self):
        # choice 成员是 seq → 加括号，防被 | 吞并
        assert serialize_production_tree(
            analyze_production_features("@A,@B|@C")
        ) == "(@A,@B)|@C"

    def test_seq(self):
        assert serialize_production_tree(
            analyze_production_features("@A,symbol.base.comma,@B")
        ) == "@A,symbol.base.comma,@B"

    def test_repeat_simple(self):
        assert serialize_production_tree(analyze_production_features("@A*")) == "@A*"

    def test_repeat_composite_parenthesized(self):
        assert serialize_production_tree(
            analyze_production_features("(@A|@B)*")
        ) == "(@A|@B)*"

    def test_optional_seq_parenthesized(self):
        assert serialize_production_tree(
            analyze_production_features("(keyword.else,@Stmt)?")
        ) == "(keyword.else,@Stmt)?"

    def test_plus(self):
        assert serialize_production_tree(analyze_production_features("@A+")) == "@A+"


class TestRoundtrip:
    @pytest.mark.parametrize(
        "prod",
        [
            "A|B",
            "@A|@B|@C",
            "@A,@B,@C",
            "(symbol.base.comma,(@AnsiPortDecl|@Identifier))*",
            "(keyword.else,@Stmt)?",
            "@PrimaryExpr|@UnaryExpr",
            "(@MulOp,@PrimaryExpr|@UnaryExpr)*",
            "symbol.base.not|symbol.base.bit_not",
            "@RangeBracket*",
            "(@AttrStmt|@Stmt)|symbol.base.semicolon",
            "(symbol.base.comma,@Declarator)*",
            "@Identifier,@ParameterList?,symbol.base.semicolon?",
        ],
    )
    def test_roundtrip_equivalence(self, prod):
        assert _roundtrip(prod), f"round-trip 不等价: {prod}"


class TestRealGrammarRoundtrip:
    def test_all_real_productions_roundtrip(self):
        """真实语法全部 production 经 analyze→serialize→analyze 树等价。"""
        from core.define import GrammarRulesRegister
        from core.plugin_loader import load_all_components

        load_all_components()
        from parser import setup_grammar
        from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS

        rules = setup_grammar(
            DEFAULT_RULES_DIR,
            GrammarRulesRegister.get_default(),
            ext_dirs=DEFAULT_EXT_DIRS,
        )
        total = 0
        for rule in rules.values():
            for prod in getattr(rule, "production", []) or []:
                if not isinstance(prod, str):
                    continue
                total += 1
                assert _roundtrip(prod), f"round-trip 不等价: {prod}"
        assert total > 400, f"覆盖不足: {total}"
