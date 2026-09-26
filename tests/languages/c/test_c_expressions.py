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


class TestCommaExpr:
    """逗号运算符（ISO C99 §6.5.17）——**分层**判据，与分隔符位点分开守。

    标准把"整个表达式"（`expression`，允许逗号）与"赋值表达式"
    （`assignment-expression`，不含逗号）分成两层。本包把逗号做成**语法形态**
    （`CommaExpr` = 显式 `,` 分隔 + 逐项 pratt 子表达式），不进 pratt 运算符表
    ——一旦入表，实参/初始化器/数组长度/枚举项/声明符的逗号会被整表 pratt 吞掉
    （见 `base/_operator.toml` §6.5.17 与 `00_expressions.toml` 的 CommaExpr 注释）。

    故本类两半各守一边：**整表达式位点**必须出 `CommaExpr`；**分隔符位点**必须
    仍是分隔符（各自 2/3 项，不被吞）。
    """

    def test_paren_comma(self, c):
        """`(a, b)` —— 标准 `( expression )`，也是逗号表达式最常见的写法。"""
        e = _expr("(a, b)", c)
        assert e.node_name == "ParenthesizedExpr"
        inner = e.expr
        assert inner.node_name == "CommaExpr"
        assert [i.node_name for i in inner.items] == ["Identifier", "Identifier"]

    def test_expr_stmt_comma(self, c):
        """`a = b, c;` —— 表达式语句整体是逗号表达式（首项是赋值）。"""
        assert _expr("a = b, c", c).node_name == "CommaExpr"

    def test_comma_items_are_full_expressions(self, c):
        """逗号各项是 pratt 子表达式（这里用加法验证各项走了优先级）。"""
        e = _expr("(a + b, c * d)", c)
        inner = e.expr
        assert [i.node_name for i in inner.items] == ["BinaryOp", "BinaryOp"]
        assert inner.items[0].op == "+" and inner.items[1].op == "*"

    def test_three_items(self, c):
        assert len(_expr("(a, b, c)", c).expr.items) == 3

    def test_bare_expression_has_no_comma_wrapper(self, c):
        """**无逗号不套壳**：选择器让普通表达式仍返回 `Expression` 本体。

        若把逗号层写成可选（`(...)*`），每个表达式语句/条件/括号都会多一层
        `CommaExpr(items=[…])`，全局 AST 形状变脸——这条钉住那个取舍。
        """
        assert _expr("a + b", c).node_name == "BinaryOp"
        assert _expr("a", c).node_name == "Identifier"

    def test_return_value_is_comma_expression(self, c):
        ast = _parse("int f(void) { return 1, 2; }\n", c)
        assert ast.sub_node[0].body.body.items[0].value.node_name == "CommaExpr"

    def test_for_clauses_allow_comma(self, c):
        """`for (i = 0, j = n; i < j; i++, j--)` —— 三段都是整表达式位点。"""
        ast = _parse(
            "int f(int n) { int i; int j; "
            "for (i = 0, j = n; i < j; i++, j--) { i++; } return i; }\n",
            c,
        )
        f = ast.sub_node[0].body.body.items[2]
        assert f.node_name == "ForStmt"
        assert f.init.node_name == "CommaExpr"
        assert f.step.node_name == "CommaExpr"

    @pytest.mark.parametrize(
        "src",
        ["if (a, b) { c++; }", "while (a, b) { c++; }", "switch (a, b) { case 1: break; }"],
    )
    def test_condition_allow_comma(self, c, src):
        """四类条件都是整表达式位点（`do` 的 while 同族，见 control_flow 测试）。"""
        ast = _parse(f"int f(void) {{ {src} return 0; }}\n", c)
        assert ast.sub_node[0].node_name == "FuncDef"

    def test_subscript_allows_comma(self, c):
        """`a[i, j]` —— 标准 `postfix-expression [ expression ]`（tree-sitter-c 这里
        比标准窄，本包照标准；见 `docs/references.md`「C 语言文法参照」）。"""
        e = _expr("a[i, j]", c)
        assert e.suffixes[0].index.node_name == "CommaExpr"


class TestCommaSeparatorsNotSwallowed:
    """**分隔符位点**的逗号必须仍是分隔符（对照上一类的"整表达式位点"）。

    这是逗号运算符最容易做坏的地方：pratt 运算符表里加一个 `,` 就能"支持逗号"，
    但会让实参表/初始化器/枚举体/声明符表**全体塌成一项**（实测枚举体 3 项 → 1 项）。
    """

    def test_call_args_stay_separate(self, c):
        e = _expr("f(a, b, c)", c)
        assert e.suffixes[0].args.items and len(e.suffixes[0].args.items) == 3

    def test_declarator_list_stays_separate(self, c):
        ast = _parse("int a = 1, b = 2, c = 3;\n", c)
        assert len(ast.sub_node[0].declarators.items) == 3

    def test_enumerator_list_stays_separate(self, c):
        ast = _parse("enum e { A, B, C };\n", c)
        body = ast.sub_node[0].specs.spec.body
        assert len(body.items) == 3

    def test_initializer_list_stays_separate(self, c):
        ast = _parse("int a[3] = {1, 2, 3};\n", c)
        init = ast.sub_node[0].declarators.items[0].init
        assert len(init.items) == 3

    def test_case_value_is_not_comma(self, c):
        """`case` 值是 constant-expression（标准层级更窄），故 `case 1:` 的值为单项。"""
        ast = _parse("int f(int a) { switch (a) { case 1: return 1; } return 0; }\n", c)
        # 找到 CaseLabel
        from core.define import iter_nodes

        labels = [n for n in iter_nodes(ast) if n.node_name == "CaseLabel"]
        assert labels and labels[0].value.node_name != "CommaExpr"

    def test_array_length_stays_single(self, c):
        """数组长度 `[ assignment-expression? ]` —— 声明符表不被吞。"""
        ast = _parse("int a[2], b;\n", c)
        assert len(ast.sub_node[0].declarators.items) == 2


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


class TestCastAndCompoundLiteral:
    """强制转换 `(T)x` 与复合字面量 `(T){…}`（C99 §6.5.4 / §6.5.2.5）——**切片 1a**。

    范围（`ROADMAP.md`「C 语义层首个切片」）：只接受**类型关键字起头**的类型名
    （`CastTypeName`，不含 `@TypedefName`）。理由：类型关键字不可能起始表达式，故与
    `(expr)` 的候选集**不交**，按 FIRST 集即可判定、不需要符号表——这是"无歧义"的
    实证，由本类第二组（**对照**）用例守着。typedef 名起头的形态（`(myint)x`）是真
    歧义（`(a)*b` 是乘法还是转换），归切片 1b（需符号表），见 `test_typedef_cast_is_1b`。
    """

    @pytest.mark.parametrize(
        "src,type_first,operand_or_init",
        [
            ("(int)x", "SimpleType", "Identifier"),
            ("(unsigned long)y", "SimpleType", "Identifier"),
            ("(char *)p", "SimpleType", "Identifier"),
            ("(struct p *)q", "StructSpecifier", "Identifier"),
            ("(enum e)v", "EnumSpecifier", "Identifier"),
            ("(_Bool)b", "SimpleType", "Identifier"),
            ("(unsigned)-1", "SimpleType", "UnaryOp"),
            ("(int)a[i]", "SimpleType", "PostfixExpr"),
        ],
    )
    def test_cast_forms(self, c, src, type_first, operand_or_init):
        e = _expr(src, c)
        assert e.node_name == "CastExpr", f"{src!r} 未成转换节点：{e.node_name}"
        assert e.type_name.first.node_name == type_first
        assert e.operand.node_name == operand_or_init

    def test_nested_cast(self, c):
        """`(int)(char)z` —— 嵌套转换靠原子最长匹配（`CastExpr` 是 is_atom）。"""
        e = _expr("(int)(char)z", c)
        assert e.node_name == "CastExpr"
        assert e.operand.node_name == "CastExpr"

    def test_cast_is_unary_precedence(self, c):
        """`(int)x * y` 必须是 `((int)x) * y`（转换是一元优先级，不吃中缀）。"""
        e = _expr("(int)x * y", c)
        assert e.node_name == "BinaryOp" and e.op == "*"
        assert e.left.node_name == "CastExpr"

    def test_cast_as_operand(self, c):
        e = _expr("a + (int)b", c)
        assert e.node_name == "BinaryOp"
        assert e.right.node_name == "CastExpr"

    @pytest.mark.parametrize(
        "src",
        ["(int){1}", "(int){1, 2}", "(struct p){1, 2}", "(struct p){.x = 1}"],
    )
    def test_compound_literal_forms(self, c, src):
        e = _expr(src, c)
        assert e.node_name == "CompoundLiteral", f"{src!r} 未成复合字面量：{e.node_name}"
        assert e.init.node_name == "InitList"

    @pytest.mark.parametrize(
        "src,want",
        [
            ("(a) * b", "BinaryOp"),
            ("(a) + b", "BinaryOp"),
            ("(a, b)", "ParenthesizedExpr"),
            ("(x + y) * z", "BinaryOp"),
        ],
    )
    def test_paren_expression_forms_not_cast(self, c, src, want):
        """**对照判据（无歧义的实证）**：括号里是表达式时**不得**判成转换。"""
        assert _expr(src, c).node_name == want, f"{src!r} 被误判成转换"

    def test_typedef_cast_is_1b(self, c):
        """typedef 名起头**不在 1a 范围**（真歧义，需符号表）：不得被静默当成转换。"""
        ast = _parse("void f(void) { (myint)x; }\n", c)
        names = [n.node_name for n in (getattr(ast, "sub_node", []) or [])]
        # 若判定为转换说明 1a 越界引入了"猜"；当前应为解析失败（空 AST）或非转换路径
        assert names == [], f"`(myint)x` 现被接受（{names}）——1a 只应覆盖关键字类型名"


class TestSizeofPrecedence:
    """`sizeof` 的**一元优先级**与"括号内是类型名"优先（C99 §6.5.3.4）。

    两处都曾是实现偏差（2026-09-25 实测）：

    1. `sizeof a * b` 旧写法把操作数当 pratt 全表达式 → 解析成 `sizeof (a*b)`；
       正确是 `(sizeof a) * b`（`sizeof` 与一元运算符同级）。修法：操作数走
       **一元层级**入口（`pratt_level = "unary"`，不吃中缀）。
    2. 引入 `CastExpr` 后 `sizeof(int) * n` 被原子路径按"消费最多"判成
       `sizeof((int) * n)`（转换形态多两个 token）；修法：`sizeof` 操作数用
       **有序分派**（先试括号类型名），与标准"括号内是类型名即按类型名解析"一致。
    """

    def test_sizeof_binds_tighter_than_multiplication(self, c):
        e = _expr("sizeof a * b", c)
        assert e.node_name == "BinaryOp" and e.op == "*"
        assert e.left.node_name == "SizeofExpr"

    def test_sizeof_type_name_wins_over_cast_reading(self, c):
        e = _expr("sizeof(int) * n", c)
        assert e.node_name == "BinaryOp" and e.op == "*"
        assert e.left.node_name == "SizeofTypeExpr", (
            f"`sizeof(int) * n` 被解析成 {e.left.node_name}——类型名形态应优先"
        )

    def test_sizeof_struct_pointer(self, c):
        e = _expr("sizeof(struct p) * n", c)
        assert e.left.node_name == "SizeofTypeExpr"

    def test_sizeof_prefix_operand(self, c):
        """`sizeof *p`（常见写法）——一元层级入口允许前缀一元。"""
        e = _expr("sizeof *p", c)
        assert e.node_name == "SizeofExpr"
        assert e.operand.node_name == "UnaryOp" and e.operand.op == "*"

    def test_sizeof_prefix_operand_binds_tighter_than_infix(self, c):
        """`sizeof *p * q` 必须是 `(sizeof *p) * q`——**前缀操作数也不吞中缀**。

        这是 `pratt_level = "unary"` 的判据样本：若操作数按 `expression` 层级解析，
        `*p * q` 会整体成为 sizeof 的操作数（`sizeof(*p * q)`）。
        """
        e = _expr("sizeof *p * q", c)
        assert e.node_name == "BinaryOp" and e.op == "*"
        assert e.left.node_name == "SizeofExpr"
        assert e.left.operand.node_name == "UnaryOp"

    def test_sizeof_postfix_operand(self, c):
        e = _expr("sizeof a[0]", c)
        assert e.operand.node_name == "PostfixExpr"

    def test_sizeof_paren_expression(self, c):
        """括号里是**明确表达式** → 一元形态。"""
        e = _expr("sizeof (a + b)", c)
        assert e.node_name == "SizeofExpr"
        assert e.operand.node_name == "ParenthesizedExpr"

    def test_sizeof_single_identifier_paren_is_wide_in(self, c):
        """`sizeof (a)` 单标识符 → 判成**类型名**（宽进，属切片 1b 面）。

        `TypeName` 含 `@TypedefName` 且类型名形态优先试——`sizeof(myint)` 要靠它。
        单标识符究竟是 typedef 名还是变量，属符号表知识（切片 1b）；本阶段记为
        **已知宽进**，由符号表落地后细化。
        """
        assert _expr("sizeof (a)", c).node_name == "SizeofTypeExpr"
