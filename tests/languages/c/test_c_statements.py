"""tests/languages/c/test_c_statements.py — C 包阶段 3 语句层（Layer A）。

Layer A 范围：原子表达式（数字/字符串/标识符/括号）+ `ExprStmt` / `EmptyStmt` /
`ReturnStmt` / `CompoundStmt` / `FuncDef`。控制流与运算符在 Layer B/C（见
`grammar/c/00_expressions.toml` 与 `03_statements.toml` 头注的 Layer 划分）。

判据双向：正样本进 AST 且**结构可查**（不许只断言"能解析"）；负样本挑"首 token 能
起始语句"的形态（否则 linter 会静默跳过，测试假绿）。
"""

import pytest

from tests.languages.c.conftest import _lint, _node_names, _parse


class TestFunctionDefinition:
    def test_minimal_function(self, c):
        """`int main(void) { return 0; }` → FuncDef，体内一条 ReturnStmt。"""
        ast = _parse("int main(void) { return 0; }\n", c)
        assert _node_names(ast) == ["FuncDef"]
        fn = ast.sub_node[0]
        assert [n.node_name for n in fn.body.body.items] == ["ReturnStmt"]

    def test_expression_statement_in_body(self, c):
        ast = _parse("void f(void) { x; }\n", c)
        body = ast.sub_node[0].body
        assert [n.node_name for n in body.body.items] == ["ExprStmt"]

    def test_empty_statement_in_body(self, c):
        ast = _parse("void f(void) { ; }\n", c)
        body = ast.sub_node[0].body
        assert [n.node_name for n in body.body.items] == ["EmptyStmt"]

    def test_multiple_statements_keep_order(self, c):
        ast = _parse("int f(void) { x; ; return x; }\n", c)
        body = ast.sub_node[0].body
        assert [n.node_name for n in body.body.items] == [
            "ExprStmt",
            "EmptyStmt",
            "ReturnStmt",
        ]

    def test_bare_return(self, c):
        """`return;` —— 返回值可选（void 函数）。"""
        ast = _parse("void f(void) { return; }\n", c)
        ret = ast.sub_node[0].body.body.items[0]
        assert ret.node_name == "ReturnStmt"

    def test_nested_compound(self, c):
        ast = _parse("void f(void) { { x; } }\n", c)
        outer = ast.sub_node[0].body
        assert [n.node_name for n in outer.body.items] == ["CompoundStmt"]

    def test_function_and_prototype_coexist(self, c):
        """原型与定义并存：`;` 结尾是声明、`{` 开头是定义。"""
        ast = _parse("int f(void);\nint f(void) { return 1; }\n", c)
        assert _node_names(ast) == ["Declaration", "FuncDef"]


class TestAtoms:
    def test_number_atom(self, c):
        ast = _parse("void f(void) { 42; }\n", c)
        stmt = ast.sub_node[0].body.body.items[0]
        assert stmt.expr.node_name == "Number"

    def test_string_atom(self, c):
        ast = _parse('void f(void) { "hi"; }\n', c)
        stmt = ast.sub_node[0].body.body.items[0]
        assert stmt.expr.node_name == "StringLiteral"

    def test_parenthesized_atom(self, c):
        ast = _parse("void f(void) { (x); }\n", c)
        stmt = ast.sub_node[0].body.body.items[0]
        assert stmt.expr.node_name == "ParenthesizedExpr"

    def test_nested_parentheses(self, c):
        ast = _parse("void f(void) { ((x)); }\n", c)
        outer = ast.sub_node[0].body.body.items[0].expr
        assert outer.node_name == "ParenthesizedExpr"
        assert outer.expr.node_name == "ParenthesizedExpr"


class TestStatementRejection:
    @pytest.mark.parametrize(
        "src",
        [
            "int f(void) { return 1 }\n",   # 缺分号
            "int f(void) { (x; }\n",        # 括号不闭合
            "int f(void) { return 1; \n",   # 函数体不闭合
        ],
    )
    def test_bad_statement_reports(self, c_linter, src):
        assert _lint(src, c_linter), f"应报错但通过了：{src!r}"
