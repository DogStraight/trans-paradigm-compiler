"""tests/languages/c/conftest.py — C 语言包共享 fixtures。

c fixture：用 load_language("grammar/c") 初始化 C 包（单语言选择模型），
测试结束恢复 verilog，避免污染其它测试（同 tests/languages/yaml/conftest.py 的
纪律：语言作用域是全局态，切走必须切回）。

⚠ **必须带 `plugins_dir`**（与 verilog 测试的惯例一致）：语言包 `tpc.toml` 的
`[plugins] enabled` 列了增量插件（c11）之后，只用 pack 路径加载会 fail-fast——
「列了插件却没扫它的清单」→ `base='plugins' 未在 load_all() 中提供`。
"""

import os

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
_PLUGINS = os.path.join(_RULES, "plugins")


@pytest.fixture(scope="module")
def c(config_loaded):
    """初始化 C 语言包（含其增量插件），测试结束恢复 verilog。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    register = GrammarRulesRegister()  # 独立实例，不污染全局单例
    rules = setup_grammar(_RULES, register, ext_dirs=[_PLUGINS])
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    parser = Parser(rules_dir=_RULES, rules=rules, rule_selector=rs, log_file="")
    lexer = Lexer(rules_dir=_RULES, ext_dirs=[_PLUGINS])
    yield {"rules": rules, "parser": parser, "lexer": lexer}
    # 恢复 verilog（语言作用域是全局态）
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


@pytest.fixture(scope="module")
def c_linter(config_loaded):
    """C 包 LinterScanner（负样本判据：不可解析的源应报错）。"""
    del config_loaded
    scanner = LinterScanner(
        rules_dir=_RULES, register=GrammarRulesRegister(), ext_dirs=[_PLUGINS]
    )
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
