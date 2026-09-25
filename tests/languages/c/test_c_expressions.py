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


class TestSizeof:
    """C99 §6.5.3.4：`sizeof ( type-name )` 与 `sizeof unary-expression` 两种形态。"""

    @pytest.mark.parametrize(
        "src",
        ["sizeof(int)", "sizeof(unsigned int)", "sizeof(struct s)", "sizeof(char *)"],
    )
    def test_sizeof_type_name(self, c, src):
        e = _expr(src, c)
        assert e.node_name == "SizeofTypeExpr", f"{src!r} -> {e.node_name}"

    def test_sizeof_type_name_multiwrd(self, c):
        """多词类型名（`sizeof(unsigned long long)`）——`TypeName` 收说明符序列。"""
        e = _expr("sizeof(unsigned long long)", c)
        assert e.node_name == "SizeofTypeExpr"
        spec = e.type_name
        assert spec.rest is not None  # 说明符余项非空（多词证据）

    @pytest.mark.parametrize("src", ["sizeof x", "sizeof a[0]", "sizeof f(y)"])
    def test_sizeof_expression(self, c, src):
        e = _expr(src, c)
        assert e.node_name == "SizeofExpr", f"{src!r} -> {e.node_name}"

    def test_sizeof_in_expression(self, c):
        """`sizeof(int) * 2` —— sizeof 是原子，参与优先级链。"""
        e = _expr("sizeof(int) * 2", c)
        assert e.node_name == "BinaryOp" and e.op == "*"
        assert e.left.node_name == "SizeofTypeExpr"

    def test_sizeof_bad_form_fails_at_parse(self, c):
        """`sizeof(` —— 残缺形态在解析层被拒（linter 对残缺形态会沉默，不作判据）。"""
        ast = _parse("void f(void) { sizeof(; }\n", c)
        assert [n.node_name for n in (getattr(ast, "sub_node", []) or [])] == []


class TestCastIsNotSupportedYet:
    """⚠ **强制转换 `(T)x` 尚未支持**（C99 §6.5.4）——钉住"报错"而非静默误解析。

    它与 `(expr)` 的区分需要**类型名知识**（T 是否为 typedef 名），属语义层信息；
    语法层猜会把 `(x)` 误判成转换。故本阶段**拒收**，留待与 typedef 名判定同批处理。
    修好后本用例会失败 → 提醒同步 `00_expressions.toml` 的"未做"清单。
    """

    def test_cast_form_is_rejected(self, c):
        ast = _parse("void f(void) { (int)x; }\n", c)
        names = [n.node_name for n in (getattr(ast, "sub_node", []) or [])]
        assert names == [], f"形态变了（现为 {names}）——若已支持强制转换，请改断言并同步 TOML 清单"
