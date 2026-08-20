"""tests/languages/verilog/test_sim_plugin.py — sim 插件：仿真语法剥离验证。

方案 B 语义：主包规则集纯净可综合（不含仿真语法），仿真语法归 plugins/sim
（默认启用，能力不损）。本测试固化两个方向的断言：
  1. 主包（不加载插件）= 不含 initial/forever/@event 等待/$display，挂载点
     CtrlStmt/CallStmt/ProcStmt 均无仿真规则引用
  2. sim 插件启用（setup_grammar 自动加载）= 4 条仿真规则经 inject 挂回挂载点，
     含 initial/$display 的源码可正常解析

用独立 GrammarRulesRegister，避免污染全局单例（c4 教训）。
"""

import pytest

from core.define import DEFAULT_RULES_DIR, GrammarRulesRegister
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from lexer import Lexer

pytestmark = pytest.mark.usefixtures("config_loaded")

SIM_RULES = ["InitialStmt", "ForeverLoop", "EventWaitStmt", "SysTaskStmt"]


def _core_only() -> dict:
    """只加载主包 0*.toml（绕过插件组件加载）——等价 sim 插件关闭。"""
    return GrammarRulesRegister().rules_registration(DEFAULT_RULES_DIR)


def _with_plugins() -> dict:
    reg = GrammarRulesRegister()
    return setup_grammar(DEFAULT_RULES_DIR, register=reg)


def _mk_parser(rules: dict) -> Parser:
    stmt_names = [
        n for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    return Parser(rules_dir=DEFAULT_RULES_DIR, rules=rules, rule_selector=rs, log_file="")


def _parse(src: str, rules: dict):
    parser = _mk_parser(rules)
    lexer = Lexer(rules_dir=DEFAULT_RULES_DIR)
    return parser.parse(lexer.tokenize(src))


def test_core_excludes_sim_rules():
    """主包规则表不含仿真规则，挂载点无仿真引用（纯净可综合）。"""
    rules = _core_only()
    for name in SIM_RULES + ["SimCtrlStmt"]:
        assert name not in rules, f"{name} 应已剥离出主包"
    assert "@ForeverLoop" not in rules["CtrlStmt"].prods[0]
    assert "@EventWaitStmt" not in rules["CtrlStmt"].prods[0]
    assert "@SysTaskStmt" not in rules["CallStmt"].prods[0]
    assert "@InitialStmt" not in rules["ProcStmt"].prods[0]


def test_plugin_injects_sim_rules():
    """sim 插件启用后仿真规则经 SimCtrlStmt 容器挂回（避免传播注入嵌套累积）。"""
    rules = _with_plugins()
    for name in SIM_RULES + ["SimCtrlStmt"]:
        assert name in rules, f"{name} 未从插件加载"
    # 挂载点：CtrlStmt 注入容器一次，仿真语句在容器内 choice
    assert "@SimCtrlStmt" in rules["CtrlStmt"].prods[0]
    container = rules["SimCtrlStmt"].prods[0]
    for ref in ["@ForkBlock", "@EventWaitStmt", "@ForeverLoop", "@DelayControlStmt",
                "@WaitStmt", "@EventTrigger", "@DisableStmt", "@ForceAssign", "@ReleaseStmt"]:
        assert ref in container, f"{ref} 不在 SimCtrlStmt 容器"
    assert "@SysTaskStmt" in rules["CallStmt"].prods[0]
    assert "@InitialStmt" in rules["ProcStmt"].prods[0]


def test_core_only_rejects_initial():
    """主包（sim 关闭）解析含 initial 的源码 truncated——仿真语法不可解析。

    parse 在 truncated 时返回部分 AST 并置 _parse_truncated 标记（不抛异常），
    以该标记断言 initial 关键字未被主包消费。
    """
    rules = _core_only()
    parser = _mk_parser(rules)
    lexer = Lexer(rules_dir=DEFAULT_RULES_DIR)
    parser.parse(lexer.tokenize("module m; initial begin clk = 1'b0; end endmodule"))
    assert parser._parse_truncated


def test_parse_initial_with_plugin():
    """sim 启用解析 initial 块成功。"""
    ast = _parse("module m; initial begin clk = 1'b0; end endmodule", _with_plugins())
    assert ast is not None


def test_parse_forever_with_plugin():
    """sim 启用解析 forever 循环成功。"""
    ast = _parse("module m; initial forever begin clk = ~clk; end endmodule", _with_plugins())
    assert ast is not None


def test_parse_display_with_plugin():
    """sim 启用解析 $display 系统任务成功。"""
    ast = _parse(
        "module m; initial $display(\"hello %d\", 42); endmodule",
        _with_plugins(),
    )
    assert ast is not None
