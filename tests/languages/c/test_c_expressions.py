"""tests/languages/c/test_c_expressions.py — C 包阶段 3 Layer B：运算符与优先级。

Layer B 范围 = `base/_operator.toml` 的运算符表（C99 §6.5 优先级/结合性/一元位置）
经 pratt 解析。本文件断言**树形**（优先级体现为嵌套关系），不是"能解析就行"。

节点形状（引擎 pratt 产出）：`BinaryOp{left, op, right}` / `UnaryOp{op, operand,
position}` / `TernaryOp{cond, then, else}`。
"""

import pytest

from tests.languages.c.conftest import _lint, _parse


def _expr(src: str, c):
    """把表达式包进函数体取表达式节点（避免另建入口规则）。"""
    ast = _parse(f"void f(void) {{ {src}; }}\n", c)
    return ast.sub_node[0].body.body.items[0].expr


class TestPrecedence:
    def test_multiplicative_binds_tighter_than_additive(self, c):
        e = _expr("a + b * c", c)
        assert e.node_name == "BinaryOp" and e.op == "+"
        assert e.right.node_name == "BinaryOp" and e.right.op == "*"

    def test_additive_binds_tighter_than_shift(self, c):
        e = _expr("a << 2 + 1", c)
        assert e.op == "<<"
        assert e.right.node_name == "BinaryOp" and e.right.op == "+"

    def test_equality_binds_tighter_than_bitand(self, c):
        e = _expr("a & b == c", c)
        assert e.op == "&"
        assert e.right.node_name == "BinaryOp" and e.right.op == "=="

    def test_logical_and_binds_tighter_than_or(self, c):
        e = _expr("!a || b && c", c)
        assert e.op == "||"
        assert e.left.node_name == "UnaryOp" and e.left.op == "!"
        assert e.right.node_name == "BinaryOp" and e.right.op == "&&"

    def test_relational_binds_tighter_than_logical_and(self, c):
        e = _expr("a && b < c", c)
        assert e.op == "&&"
        assert e.right.node_name == "BinaryOp" and e.right.op == "<"


class TestAssociativity:
    def test_assignment_is_right_associative(self, c):
        e = _expr("a = b = c", c)
        assert e.op == "="
        assert e.right.node_name == "BinaryOp" and e.right.op == "="

    def test_compound_assignment(self, c):
        e = _expr("a += b", c)
        assert e.op == "+="

    def test_subtraction_is_left_associative(self, c):
        """`a - b - c` → ((a-b)-c)：外层右侧应是原子，左侧才是 BinaryOp。"""
        e = _expr("a - b - c", c)
        assert e.op == "-"
        assert e.left.node_name == "BinaryOp" and e.left.op == "-"
        assert e.right.node_name == "Identifier"


class TestUnaryAndPostfix:
    @pytest.mark.parametrize("op", ["-", "+", "!", "~", "*", "&"])
    def test_prefix_operators(self, c, op):
        e = _expr(f"{op}a", c)
        assert e.node_name == "UnaryOp"
        assert e.op == op and e.position == "prefix"

    @pytest.mark.parametrize("op", ["++", "--"])
    def test_postfix_operators(self, c, op):
        e = _expr(f"a{op}", c)
        assert e.node_name == "UnaryOp"
        assert e.op == op and e.position == "postfix"

    def test_deref_of_parenthesized(self, c):
        e = _expr("*(a)", c)
        assert e.node_name == "UnaryOp" and e.op == "*"
        assert e.operand.node_name == "ParenthesizedExpr"


class TestConditional:
    def test_ternary(self, c):
        e = _expr("a ? b : c", c)
        assert e.node_name == "TernaryOp"

    def test_ternary_nested_in_assignment(self, c):
        e = _expr("x = a ? b : c", c)
        assert e.op == "="
        assert e.right.node_name == "TernaryOp"


class TestExpressionRejection:
    @pytest.mark.parametrize(
        "src",
        [
            "void f(void) { a + ; }\n",       # 二元右操作数缺失
            "void f(void) { a ? b; }\n",      # 三目缺 `:`
            "void f(void) { a b; }\n",        # 两个表达式相邻（缺运算符）
        ],
    )
    def test_bad_expression_reports(self, c_linter, src):
        assert _lint(src, c_linter), f"应报错但通过了：{src!r}"
