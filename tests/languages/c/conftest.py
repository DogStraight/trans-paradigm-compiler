"""tests/languages/c/conftest.py — C 语言包共享 fixtures。

c fixture：用 load_language("grammar/c") 初始化 C 包（单语言选择模型），
测试结束恢复 verilog，避免污染其它测试（同 tests/languages/yaml/conftest.py 的
纪律：语言作用域是全局态，切走必须切回）。
"""

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from parser import setup_grammar
from parser.rule_selector import RuleSelector
from parser.parser_core import Parser
from lexer import Lexer
from linter.scanner import LinterScanner

# 测试文件经 `from tests.languages.c.conftest import _parse, _node_names` 导入
__all__ = ["_parse", "_node_names", "_lint"]

_RULES = "grammar/c"


@pytest.fixture(scope="module")
def c(config_loaded):
    """初始化 C 语言包（单语言选择），测试结束恢复 verilog。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    ConfigRegistry.load_language(_RULES)
    register = GrammarRulesRegister()  # 独立实例，不污染全局单例
    rules = setup_grammar(_RULES, register)
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    parser = Parser(rules_dir=_RULES, rules=rules, rule_selector=rs, log_file="")
    lexer = Lexer(rules_dir=_RULES)
    yield {"rules": rules, "parser": parser, "lexer": lexer}
    # 恢复 verilog（语言作用域是全局态）
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


@pytest.fixture(scope="module")
def c_linter(config_loaded):
    """C 包 LinterScanner（负样本判据：不可解析的源应报错）。"""
    del config_loaded
    scanner = LinterScanner(rules_dir=_RULES, register=GrammarRulesRegister())
    yield scanner
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _parse(src: str, c):
    """C 源码 → AST。"""
    tokens = c["lexer"].tokenize(src)
    return c["parser"].parse(tokens)


def _node_names(ast) -> list[str]:
    """AST 顶层节点名列表。"""
    return [n.node_name for n in getattr(ast, "sub_node", []) or []]


def _lint(src: str, c_linter):
    """Linter 诊断（负样本：应非空）。"""
    return c_linter.scan(src)
