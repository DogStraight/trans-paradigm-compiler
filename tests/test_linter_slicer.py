"""Linter 语法切片（grammar_slicer）单元测试 — 切片树与 first 集推导。

固化 build_slice_tree / _collect_first_start_tokens 的契约（配置驱动无硬编码）：
    - 块规则 block_start/block_end 从 production 剥离，但 call 引用时并入 firsts
      （@BeginEnd → keyword.begin，e15 修复的核心——first 集喂给 matcher 的
      起始校验与 lookahead 的前缀判别）
    - Stmt 选择器 firsts 穿透块规则含 keyword.begin（@Stmt 起始校验需要）
    - 各 feature 类型（token/choice/seq/optional/repeat）的 first 集推导
"""

import pytest

from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS, GrammarRulesRegister
from parser import setup_grammar
from linter.grammar_slicer import build_slice_tree, _collect_first_start_tokens


@pytest.fixture(scope="module")
def tree(config_loaded):
    rules = setup_grammar(
        DEFAULT_RULES_DIR,
        GrammarRulesRegister.get_default(),
        ext_dirs=DEFAULT_EXT_DIRS,
    )
    return build_slice_tree(rules)


class TestSliceTreeStructure:
    """切片树结构字段（block_start/block_end/is_* 从 GrammarRule 透传）。"""

    def test_block_rule_fields(self, tree):
        info = tree["BeginEnd"]
        assert info["is_block"] is True
        assert info["block_start"] == "keyword.begin"
        assert info["block_end"] == "keyword.end"

    def test_module_decl_fields(self, tree):
        info = tree["ModuleDecl"]
        assert info["is_block"] is True
        assert info["block_start"] == "keyword.module"
        assert info["block_end"] == "keyword.endmodule"

    def test_statement_rule_fields(self, tree):
        assert tree["AssignStmt"]["is_statement"] is True
        assert tree["AssignStmt"]["is_block"] is False


class TestCallBlockStartPropagation:
    """call 引用块规则 → first 集并入 block_start（e15 修复核心）。"""

    def test_beginend_call_first_includes_begin(self, tree):
        assert _collect_first_start_tokens(
            {"type": "call", "name": "BeginEnd"}, tree
        ) == {"keyword.begin"}

    def test_alwaysstmt_call_first(self, tree):
        assert _collect_first_start_tokens(
            {"type": "call", "name": "AlwaysStmt"}, tree
        ) == {"keyword.always"}


class TestStmtSelectorFirsts:
    def test_stmt_firsts_include_block_start(self, tree):
        # Stmt 选择器 firsts 穿透块规则含 begin（@Stmt 起始校验）
        firsts: set[str] = set()
        for p in tree["Stmt"]["prods"]:
            firsts |= _collect_first_start_tokens(p, tree)
        assert "keyword.begin" in firsts


class TestFirstTokenDerivation:
    """各 feature 类型的 first 集推导（配置驱动，语言无关）。"""

    def test_token(self, tree):
        assert _collect_first_start_tokens(
            {"type": "token", "token_type": "symbol.base.semicolon"}, tree
        ) == {"symbol.base.semicolon"}

    def test_choice_union(self, tree):
        choice = {
            "type": "choice",
            "alternatives": [
                {"type": "token", "token_type": "keyword.if"},
                {"type": "token", "token_type": "keyword.case"},
            ],
        }
        assert _collect_first_start_tokens(choice, tree) == {
            "keyword.if",
            "keyword.case",
        }

    def test_seq_first_element(self, tree):
        seq = {
            "type": "seq",
            "items": [
                {"type": "token", "token_type": "keyword.if"},
                {"type": "token", "token_type": "bracket.l_parentheses"},
            ],
        }
        assert _collect_first_start_tokens(seq, tree) == {"keyword.if"}

    def test_optional_empty(self, tree):
        # optional 第一 token 非强制起始 → 空集
        opt = {
            "type": "optional",
            "elem": {"type": "token", "token_type": "keyword.begin"},
        }
        assert _collect_first_start_tokens(opt, tree) == set()

    def test_repeat_first(self, tree):
        rep = {
            "type": "repeat",
            "elem": {"type": "token", "token_type": "symbol.base.comma"},
        }
        assert _collect_first_start_tokens(rep, tree) == {"symbol.base.comma"}
