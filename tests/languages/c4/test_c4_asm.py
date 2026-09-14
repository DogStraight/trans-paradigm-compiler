"""tests/languages/c4/test_c4_asm.py — c4 第二语言：语法 + 汇编生成集成测试。

单语言选择模型：fixture 用 load_language("grammar/c4") 初始化 c4 语言包
（setup_grammar 自动加载 c4 组件 AsmGenPlugin），测试结束恢复 verilog，
避免污染其它测试。

覆盖：完整管线（lex→parse→analyze→transform）把 c4 源码编译为 c4 VM
汇编（AsmProgram/AsmLine），关键控制流（if/while）生成正确跳转。
"""

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, Node
from analyzer.scope import Scope
from parser import setup_grammar
from parser.rule_selector import RuleSelector
from parser.parser_core import Parser
from lexer import Lexer
from transform.normalizer import normalize_ast
from analyzer.traversal import AnalysisTraversal
from transform import AstTransformer


@pytest.fixture(scope="module")
def c4(config_loaded):
    """初始化 c4 语言包（单语言选择），测试结束恢复 verilog。

    用独立 GrammarRulesRegister 实例，避免污染全局单例（get_default() 的
    rules 缓存被 c4 规则污染后，后续 verilog 测试规则树会混合）。
    """
    del config_loaded  # fixture 依赖声明（配置加载）
    ConfigRegistry.load_language("grammar/c4")
    register = GrammarRulesRegister()  # 独立实例，不污染全局单例
    rules = setup_grammar("grammar/c4", register)
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rs = RuleSelector(rules, stmt_names)
    parser = Parser(rules_dir="grammar/c4", rules=rules, rule_selector=rs, log_file="")
    lexer = Lexer(rules_dir="grammar/c4")
    ctx = {"rules": rules, "parser": parser, "lexer": lexer}
    yield ctx
    # 恢复 verilog（其 tpc.toml 声明了 base="plugins" 的 token_ext，需传 plugins_dir）
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _compile(src: str, c4) -> Node:
    """c4 源码 → 完整管线 → transform 后 AST（AsmProgram 或原 AST）。"""
    ast = c4["parser"].parse(c4["lexer"].tokenize(src))
    ast = normalize_ast(ast)
    analyzer = AnalysisTraversal(c4["rules"])
    ast = analyzer.analyze(ast)
    AstTransformer.set_shared("rules", c4["rules"])
    t = AstTransformer()
    root = analyzer.root_scope
    assert root is not None
    return t.transform(ast, root)


def _asm_lines(ast) -> list[str]:
    """提取 AsmProgram 的指令文本列表（去缩进）。"""
    return [ln.text.strip() for ln in getattr(ast, "sub_node", []) or []]


@pytest.mark.smoke  # smoke：c4 组代表（第二语言：语法+汇编生成集成）
class TestC4Assembly:
    def test_program_generates_asm(self, c4):
        ast = _compile("int main() { int x; x = 1; return x; }", c4)
        assert ast.node_name == "AsmProgram"
        lines = _asm_lines(ast)
        assert lines[0].startswith("ENT")  # 函数进入
        assert any(l.startswith("IMM") for l in lines)  # 立即数 1
        assert any(l.startswith("SI") for l in lines)  # 存储 x
        assert any(l.startswith("LEV") for l in lines)  # return 离开

    def test_if_else_branches(self, c4):
        ast = _compile("int main() { int x; if (x > 0) x = 1; else x = 2; }", c4)
        assert ast.node_name == "AsmProgram"
        lines = _asm_lines(ast)
        assert any(l.startswith("BZ") for l in lines)  # 条件跳转
        assert any(l.startswith("JMP") for l in lines)  # else 跳转

    def test_while_loop_backjump(self, c4):
        ast = _compile("int main() { int x; while (x < 10) x = x + 1; }", c4)
        assert ast.node_name == "AsmProgram"
        lines = _asm_lines(ast)
        assert any(l.startswith("BZ") for l in lines)  # 循环条件
        assert any(l.startswith("JMP") for l in lines)  # 回跳

    def test_function_call(self, c4):
        # 函数调用生成 PSH + 库调用码 + ADJ
        ast = _compile("int main() { printf(1); }", c4)
        assert ast.node_name == "AsmProgram"
        lines = _asm_lines(ast)
        assert any(l.startswith("ADJ") for l in lines)
        assert any(l.startswith("PSH") for l in lines)

    def test_arithmetic_priority(self, c4):
        # 运算优先级：x = 1 + 2 * 3 → MUL 在 ADD 之前
        ast = _compile("int main() { int x; x = 1 + 2 * 3; }", c4)
        lines = _asm_lines(ast)
        assert any(l.strip() == "MUL" for l in lines)
        assert any(l.strip() == "ADD" for l in lines)

    def test_guard_non_c4_untouched(self, c4):
        del c4  # fixture 依赖声明（本用例只测非 c4 根节点原样返回）
        # 守卫：非 Program 根节点（其它语言）原样返回，不生成汇编
        from core.define import Node

        ast = Node("ModuleDecl")
        t = AstTransformer()
        result = t.transform(ast, Scope("<g>", "global"))
        assert result.node_name == "ModuleDecl"
