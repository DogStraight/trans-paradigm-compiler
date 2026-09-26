"""tests/languages/c/test_c_postfix.py — C 包后缀链（C99 §6.5.2 postfix-expression）。

形状：`PostfixExpr{base, suffixes}` —— 原子 + 后缀**链**（`a.b.c` / `f(x)[i]` /
`p->a[i]` / `(*fp)(x)`）。三种后缀各一规则：`IndexSuffix` / `CallSuffix` /
`MemberSuffix`。

⚠ 与旧形状的区别（2026-09-25 改）：旧实现是三个**单级**规则（`CallExpr` 的 base 只能
是 `@Identifier`、`IndexExpr` 用组量词勉强支持 `a[i][j]`、`MemberExpr` 单级），故
`a.b.c` / `f(a)[i]` / `p->a[i]` / `(*fp)(x)` 都不支持（旧测试把它们钉成"应报错"）。
标准是左递归，本仓递归下降表达不了，改用"原子 + 后缀+"同族形态（与 clang 手写
`ParsePostfixExpressionSuffix` 的"leading part + 后缀循环"同形）。
"""

import pytest

from tests.languages.c.conftest import _lint, _parse


def _expr(src: str, c):
    ast = _parse(f"void f(void) {{ {src}; }}\n", c)
    return ast.sub_node[0].body.body.items[0].expr


def _suffix_names(e) -> list[str]:
    return [s.node_name for s in e.suffixes]


class TestSingleSuffix:
    """单后缀：链长为 1（形状与旧 CallExpr/IndexExpr/MemberExpr 对得上）。"""

    def test_call_with_args(self, c):
        e = _expr("f(a, b)", c)
        assert e.node_name == "PostfixExpr"
        assert e.base.node_name == "Identifier" and e.base.content == "f"
        assert _suffix_names(e) == ["CallSuffix"]
        assert len(e.suffixes[0].args.items) == 2

    def test_call_without_args(self, c):
        """`f()` —— 实参表是**可选**位点，空时不应挂载（也不要断言"值为空 list"）。"""
        e = _expr("f()", c)
        assert _suffix_names(e) == ["CallSuffix"]
        assert getattr(e.suffixes[0], "args", None) is None

    def test_single_index(self, c):
        e = _expr("a[i]", c)
        assert e.base.content == "a"
        assert _suffix_names(e) == ["IndexSuffix"]
        assert e.suffixes[0].index.node_name == "Identifier"

    def test_dot_access(self, c):
        e = _expr("a.b", c)
        assert e.base.content == "a"
        assert _suffix_names(e) == ["MemberSuffix"]
        assert e.suffixes[0].access.value == "."
        assert e.suffixes[0].member.content == "b"

    def test_arrow_access(self, c):
        e = _expr("p->q", c)
        assert _suffix_names(e) == ["MemberSuffix"]
        assert e.suffixes[0].access.value == "->"
        assert e.suffixes[0].member.content == "q"


class TestChainedSuffix:
    """链式后缀：≥2 个后缀（旧实现整族不支持，见文件头注）。"""

    @pytest.mark.parametrize(
        "src,base,suffixes",
        [
            ("a.b.c", "a", ["MemberSuffix", "MemberSuffix"]),
            ("p->q->r", "p", ["MemberSuffix", "MemberSuffix"]),
            ("a[i][j]", "a", ["IndexSuffix", "IndexSuffix"]),
            ("f(x)[i]", "f", ["CallSuffix", "IndexSuffix"]),
            ("p->a[i]", "p", ["MemberSuffix", "IndexSuffix"]),
            ("a[i].b", "a", ["IndexSuffix", "MemberSuffix"]),
            ("a.b[i].c", "a", ["MemberSuffix", "IndexSuffix", "MemberSuffix"]),
            ("f(x)(y)", "f", ["CallSuffix", "CallSuffix"]),
        ],
    )
    def test_chain_shape(self, c, src, base, suffixes):
        e = _expr(src, c)
        assert e.node_name == "PostfixExpr", f"{src!r} 未形成后缀链：{e.node_name}"
        assert e.base.node_name == "Identifier" and e.base.content == base
        assert _suffix_names(e) == suffixes, f"{src!r} 后缀序列不对"

    def test_call_result_indexed(self, c):
        """`f(a)[i]`（旧实现下半句钉成"应报错"，现为正向判据）。"""
        e = _expr("g(a)[i]", c)
        assert _suffix_names(e) == ["CallSuffix", "IndexSuffix"]
        assert e.suffixes[1].index.content == "i"

    def test_paren_head_call(self, c):
        """`(*fp)(x)` —— head 是括号表达式（经函数指针调用），旧实现不支持。"""
        e = _expr("(*fp)(x)", c)
        assert e.node_name == "PostfixExpr"
        assert e.base.node_name == "ParenthesizedExpr"
        assert _suffix_names(e) == ["CallSuffix"]

    def test_index_expression_is_full_expression(self, c):
        """下标里是完整表达式（这里用乘法验证走了 pratt）。"""
        e = _expr("a[i * 2]", c)
        idx = e.suffixes[0].index
        assert idx.node_name == "BinaryOp" and idx.op == "*"

    def test_call_arg_is_full_expression(self, c):
        e = _expr("f(a * b)", c)
        arg = e.suffixes[0].args.items[0]
        assert arg.node_name == "BinaryOp" and arg.op == "*"

    def test_nested_chain_in_call_arg(self, c):
        """实参自身也是链（`f(a.b.c)`）——链可嵌在链里。"""
        e = _expr("f(a.b.c)", c)
        inner = e.suffixes[0].args.items[0]
        assert inner.node_name == "PostfixExpr"
        assert _suffix_names(inner) == ["MemberSuffix", "MemberSuffix"]


class TestPostfixInContext:
    """与运算符/其他语法的复合。"""

    def test_chain_in_binary(self, c):
        e = _expr("p->key + 1", c)
        assert e.node_name == "BinaryOp" and e.op == "+"
        assert e.left.node_name == "PostfixExpr"

    def test_chain_on_assign_left(self, c):
        e = _expr("r->head = 0", c)
        assert e.node_name == "BinaryOp" and e.op == "="
        assert e.left.node_name == "PostfixExpr"

    def test_chain_inside_condition_parens(self, c):
        """`switch (p->key)` / `if (a.b)` 形态：链后随 `)`。

        回归：`PostfixExpr` 若不被任何规则引用，派生 FOLLOW 只剩运算符族 →
        后随 `)` 的形态被 FOLLOW 硬检查拦掉（实测 `ring_buffer.c` 的 `ring_scan`
        整函数解析失败）。故 `PrimaryExpr` 交替里必须引用它。
        """
        ast = _parse("int f(struct p *q) { if (q->x) { return 1; } return 0; }\n", c)
        assert ast.sub_node[0].node_name == "FuncDef"

    def test_postfix_increment_on_chain(self, c):
        """`a[i]++` —— 后缀 `++` 是 pratt 运算符（不走链），与链复合。"""
        e = _expr("a[i]++", c)
        assert e.node_name == "UnaryOp" and e.position == "postfix"
        assert e.operand.node_name == "PostfixExpr"

    def test_chain_under_sizeof(self, c):
        e = _expr("sizeof a[0]", c)
        assert e.node_name == "SizeofExpr"
        assert e.operand.node_name == "PostfixExpr"

    def test_bare_atom_stays_bare(self, c):
        """裸原子**不**被包成链（`suffixes+` 的作用：AST 形状不因加链而变脸）。"""
        assert _expr("a", c).node_name == "Identifier"
        assert _expr("42", c).node_name == "Number"
        assert _expr("(a)", c).node_name == "ParenthesizedExpr"

    def test_postfix_follow_includes_closing_brackets(self, c):
        """**不变式**：`PostfixExpr` 必须被某处**引用**——判据是派生 FOLLOW 里有右括号。

        FOLLOW 由"谁引用本规则"推导。实测（2026-09-25）：链规则若不被任何规则引用，
        其 FOLLOW 只剩 pratt 注入的运算符族 → 后随 `)` 的形态被 FOLLOW 硬检查拦掉，
        `ring_buffer.c` 的 `ring_scan`（`switch (p->key)`）**整函数解析失败**。
        故这条断言"FOLLOW 含 `bracket.r_*`"，等价于"链规则确有引用点"。
        """
        follows = getattr(c["parser"], "_follows", {}) or {}
        got = set(follows.get("PostfixExpr") or ())
        assert any(t.startswith("bracket.r_") for t in got), (
            f"FOLLOW(PostfixExpr) 不含右括号族（{sorted(got)}）——"
            "说明链规则没有被任何规则引用（FOLLOW 由引用推导）"
        )


class TestPostfixRejection:
    @pytest.mark.parametrize(
        "src",
        [
            "f(a",          # 调用括号不闭合
            "a[",           # 下标不闭合
            "a.",           # 成员名缺失
            "a->",          # 成员名缺失（箭头）
        ],
    )
    def test_bad_postfix_reports(self, c_linter, src):
        assert _lint(f"void f(void) {{ {src}; }}\n", c_linter), f"应报错但通过了：{src!r}"
