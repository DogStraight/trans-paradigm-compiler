"""tests/languages/c/test_c_postfix.py — C 包阶段 3 Layer B2：后缀链（调用/下标/成员）。"""

import pytest

from tests.languages.c.conftest import _lint, _parse


def _expr(src: str, c):
    ast = _parse(f"void f(void) {{ {src}; }}\n", c)
    return ast.sub_node[0].body.body.items[0].expr


class TestCallExpr:
    def test_call_with_args(self, c):
        e = _expr("f(a, b)", c)
        assert e.node_name == "CallExpr"
        assert e.callee.content == "f"
        assert len(e.args.items) == 2

    def test_call_without_args(self, c):
        """`f()` —— 实参表是**可选**位点，空时不应挂载（也不要断言"值为空 list"）。"""
        e = _expr("f()", c)
        assert e.node_name == "CallExpr"
        assert getattr(e, "args", None) is None

    def test_call_arg_is_expression(self, c):
        """实参是完整表达式（这里用乘法验证实参内部走了 pratt）。"""
        e = _expr("f(a * b)", c)
        arg = e.args.items[0]
        assert arg.node_name == "BinaryOp" and arg.op == "*"

    def test_call_in_binary(self, c):
        e = _expr("f(a) + 1", c)
        assert e.node_name == "BinaryOp" and e.op == "+"
        assert e.left.node_name == "CallExpr"


class TestIndexExpr:
    def test_single_index(self, c):
        e = _expr("a[i]", c)
        assert e.node_name == "IndexExpr"
        assert e.base.content == "a"

    def test_chained_index(self, c):
        """`a[i][j]` —— 组 + 量词表达链式下标（形状与 c4 同：indexes 是列表）。"""
        e = _expr("a[i][j]", c)
        assert e.node_name == "IndexExpr"
        assert len(e.indexes) == 2

    def test_index_of_call_result_is_not_supported_yet(self, c_linter):
        """`f(a)[i]`（调用结果再下标）**本层不支持**——链式后缀需要"原子 + 后缀*"形态，
        与环保护冲突。此处断言它**报错**而不是静默接受，避免"看起来支持"。"""
        assert _lint("void f(void) { g(a)[i]; }\n", c_linter)


class TestMemberExpr:
    def test_dot_access(self, c):
        e = _expr("a.b", c)
        assert e.node_name == "MemberExpr"
        assert e.base.content == "a"
        assert e.member.content == "b"

    def test_arrow_access(self, c):
        e = _expr("p->q", c)
        assert e.node_name == "MemberExpr"
        assert e.member.content == "q"

    def test_member_in_binary(self, c):
        e = _expr("s.x + 1", c)
        assert e.node_name == "BinaryOp"
        assert e.left.node_name == "MemberExpr"


class TestPostfixRejection:
    @pytest.mark.parametrize(
        "src",
        [
            "f(a",          # 调用括号不闭合
            "a[",           # 下标不闭合
            "a.",           # 成员名缺失
        ],
    )
    def test_bad_postfix_reports(self, c_linter, src):
        assert _lint(f"void f(void) {{ {src}; }}\n", c_linter), f"应报错但通过了：{src!r}"
