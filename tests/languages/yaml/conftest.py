"""tests/languages/yaml/conftest.py — yaml 语言包共享 fixtures。

yaml fixture：用 load_language("grammar/yaml") 初始化 yaml 语言包（单语言
选择模型），测试结束恢复 verilog，避免污染其它测试。
（从 test_yaml.py 提升：test_yaml.py 与 test_yaml_flow.py 共享。）
"""

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from parser import setup_grammar
from parser.rule_selector import RuleSelector
from parser.parser_core import Parser
from lexer import Lexer
from renderer import Renderer

# 测试文件经 `from tests.languages.yaml.conftest import _parse` 导入这两个
# 助手——显式导出清单（Pylance 的"未存取函数"不接受 ignore 抑制）
__all__ = ["_parse", "_node_names"]


@pytest.fixture(scope="module")
def yaml(config_loaded):
    """初始化 yaml 语言包（单语言选择），测试结束恢复 verilog。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    ConfigRegistry.load_language("grammar/yaml")
    register = GrammarRulesRegister()  # 独立实例，不污染全局单例
    rules = setup_grammar("grammar/yaml", register)
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    parser = Parser(rules_dir="grammar/yaml", rules=rules, rule_selector=rs, log_file="")
    lexer = Lexer(rules_dir="grammar/yaml")
    renderer = Renderer(rules_dir="grammar/yaml")
    yield {"rules": rules, "parser": parser, "lexer": lexer, "renderer": renderer}
    # 恢复 verilog
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _parse(src: str, yaml):
    """YAML 源码 → AST。

    auto 缩进模式：把 lexer 锁定的缩进单位盖到根节点（_indent_unit），
    renderer.render 读到后按同单位渲染——渲染输出与源文件缩进风格一致
    （块标量逐字内容相对列对齐不被破坏）。
    """
    lexer = yaml["lexer"]
    tokens = lexer.tokenize(src)
    ast = yaml["parser"].parse(tokens)
    unit = getattr(lexer, "_indent_unit", None)
    if isinstance(unit, int) and unit > 0:
        ast.add_attr("_indent_unit", unit)
    return ast


def _node_names(ast) -> list[str]:
    """提取 AST 顶层节点名列表。"""
    return [n.node_name for n in getattr(ast, "sub_node", []) or []]
