"""tests/languages/c4/test_c4_index_expr.py — c4 下标表达式（IndexExpr）解析判据。

回归背景（2026-XX，实测）：`IndexExpr` 把 `@Expression` 放在
`(bracket.l_square_bracket,@Expression,bracket.r_square_bracket)+` 的**组内**，
原 FOLLOW 推导只扫规则顶层元素列表 ⇒ `FOLLOW(Expression)` 与它下游的 atom 链
（`Identifier`/`Number`/`CallExpr`/`ParenthesizedExpr`/`SizeofExpr`/…）都缺
`bracket.r_square_bracket`，于是 **9 个下标形态在匹配期被 FOLLOW 检查拒绝**
（加载期不报错，表现为 `parse truncated (unconsumed tokens)`）。

修 `parser/follow.py::_propagate_seq`（结构级递归 `_propagate_intra`）后 9 例全部
恢复；`a[0]` / `a[i]` 这类**字面量/标识符下标**在原缺陷态之所以"看起来正常"，
是 pratt 内置字面量前缀（`pratt_parser._literal_prefix_node`）绕过了规则匹配、
也就绕过了 FOLLOW 检查——本文件的对照用例把它们一并钉住，防将来回归。

判据口径按本目录既有惯例：解析进 AST + `Parser._parse_truncated` 标记
（不新造渲染/linter harness；渲染保真由 tests/languages/c4 既有用例族覆盖）。
"""

import pytest

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister, Node
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector

# 缺陷态被 FOLLOW 检查拒绝的 9 个形态（下标表达式需要**规则匹配**的 atom）
_NESTED_ATOM_INDEXES = [
    "a[(0)]",          # 括号表达式
    "a[(i)]",
    "a[f(1)]",         # 函数调用
    "a[f()]",
    "a[a[0]]",         # 嵌套下标
    "a[b[i]]",
    "a[sizeof(int)]",  # sizeof
    "a[0][f(1)]",      # 链式：第二个下标是调用
    "a[f(1)][0]",      # 链式：第一个下标是调用
]

# 对照：缺陷态即通过（pratt 内置字面量前缀掩盖），修后不得回归
_LITERAL_INDEXES = [
    "a[0]",
    "a[i]",
    "a[10]",
    'a["s"]',
    "a[i + 1]",
    "a[0][1]",
    "a[-1]",
]

_REJECTED = ["a[]", "a[0", "a[0]]"]


@pytest.fixture(scope="module")
def c4(config_loaded):
    """初始化 c4 语言包（单语言选择），测试结束恢复 verilog 避免污染后续模块。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    ConfigRegistry.load_language("grammar/c4")
    rules = setup_grammar("grammar/c4", GrammarRulesRegister())
    stmt_names = [n for n, r in rules.items() if r.has_pass_end_case()]
    parser = Parser(
        rules_dir="grammar/c4",
        rules=rules,
        rule_selector=RuleSelector(rules, stmt_names),
        log_file="",
    )
    lexer = Lexer(rules_dir="grammar/c4")
    yield {"rules": rules, "parser": parser, "lexer": lexer}
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _assign(expr: str, c4):
    """把 `<expr>` 包成最小 c4 程序（`b = <expr>;`）解析 → (ast, truncated)。"""
    src = f"int main() {{ int a; int b; int i; int f; b = {expr}; return b; }}"
    ast = c4["parser"].parse(c4["lexer"].tokenize(src))
    return ast, c4["parser"]._parse_truncated


def _node_names(node) -> list[str]:
    """递归收集节点名（含**属性绑定**子节点，不只 sub_node）。"""
    out: list[str] = []

    def walk(n) -> None:
        out.append(getattr(n, "node_name", "?"))
        for v in n.__dict__.values():
            if isinstance(v, Node):
                walk(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, Node):
                        walk(item)
        for child in getattr(n, "sub_node", None) or []:
            walk(child)

    if node is not None:
        walk(node)
    return out


class TestC4IndexExprAccepted:
    @pytest.mark.parametrize("expr", _NESTED_ATOM_INDEXES)
    def test_nested_atom_index_parses(self, expr, c4):
        """FOLLOW 修好后：需要规则匹配 atom 的下标形态必须完整解析。"""
        ast, truncated = _assign(expr, c4)
        assert not truncated, f"{expr} 应完整解析（parse truncated）"
        assert "IndexExpr" in _node_names(ast), f"{expr} 应产出 IndexExpr 节点"

    @pytest.mark.parametrize("expr", _LITERAL_INDEXES)
    def test_literal_index_no_regression(self, expr, c4):
        """对照：原本可解析的字面量/标识符下标不得回归。"""
        ast, truncated = _assign(expr, c4)
        assert not truncated, f"{expr} 不应回归为截断"
        assert "IndexExpr" in _node_names(ast), f"{expr} 应产出 IndexExpr 节点"


class TestC4IndexExprRejected:
    @pytest.mark.parametrize("expr", _REJECTED)
    def test_malformed_index_rejected(self, expr, c4):
        """反样本：残缺/多余的方括号必须仍被拒（修 FOLLOW 不得放宽语法）。"""
        _, truncated = _assign(expr, c4)
        assert truncated, f"{expr} 应被拒（parse truncated）"


class TestC4IndexExprFollow:
    def test_rsquare_in_index_atom_follow(self, c4):
        """缺项锚点：`]` 必须进表达式链内 atom 规则的 FOLLOW（本回归的根因）。"""
        follows = c4["parser"]._follows
        for rule in ("Expression", "PrimaryExpr", "Identifier", "Number", "CallExpr"):
            assert "bracket.r_square_bracket" in follows[rule], f"FOLLOW({rule}) 缺 ']'"
