"""tests/languages/c/test_c_declarations.py — C 包阶段 1：声明与声明符。

阶段 1 范围（`docs/gaps/gap-language-pack-scope.md`「C 语言包」）：词法 + 类型
说明符与**声明符**；**不含表达式与语句**（初始化器、函数体、数组长度表达式在
阶段 2/3）。故本文件的样本都是**外部声明序列**。

判据是**双向**的（阶段 0 定）：正样本必须进 AST（只测"不报错"会漏掉规则没接上），
负样本必须被拒（只测正样本会漏掉"语法过宽"）。

⚠ 本轮实测教训（防重踩）：`Identifier` **不是引擎内置规则**，语言包必须自己
定义（c4/yaml/verilog 都各自定义一份）。漏定义时 `@Identifier` 匹配为空，症状是
"parser 报 match_length 0 / linter 报 expected ';' got 'id'"——**看起来像规则形态
问题**，实为规则缺失（本轮为此白白证伪了五个形态假设）。

⚠ 说明符**组合合法性**（`long long int` 合法 / `float int` 非法）**不在语法层**判定
——语法层宽进、语义层收，故 `float int x;` 在本阶段**应当解析通过**，见
`test_specifier_combination_is_semantic_not_syntactic`。
"""

import pytest

from tests.languages.c.conftest import _lint, _node_names, _parse


class TestDeclarationParse:
    """正样本：声明进 AST，且声明符结构可查。"""

    def test_single_declaration(self, c):
        ast = _parse("int x;\n", c)
        assert _node_names(ast) == ["Declaration"]
        decl = ast.sub_node[0]
        assert decl.declarators.items[0].declarator.direct.head.content == "x"

    def test_declaration_list(self, c):
        ast = _parse("int a, b, c;\n", c)
        decl = ast.sub_node[0]
        assert decl.declarators.items[0].declarator.direct.head.content == "a"
        assert len(decl.declarators.items) == 3  # b, c

    def test_pointer_declarator(self, c):
        ast = _parse("int *p;\nchar **pp;\n", c)
        first, second = ast.sub_node
        assert first.declarators.items[0].declarator.pointers.node_name == "Pointer"
        assert second.declarators.items[0].declarator.direct.head.content == "pp"

    def test_specifier_order_is_free(self, c):
        """`const char *s;` 与 `char const *s;` 都应通过（顺序自由）。"""
        ast = _parse("const char *s;\nchar const *t;\n", c)
        assert _node_names(ast) == ["Declaration", "Declaration"]

    def test_multiword_type_specifier(self, c):
        ast = _parse("unsigned long long big;\n", c)
        decl = ast.sub_node[0]
        assert decl.specs.node_name == "TypeSpecifier"
        assert len(decl.rest.items) == 2  # long long（首词在 specs，余项在 rest）

    def test_array_suffix(self, c):
        ast = _parse("int a[10];\nint b[];\n", c)
        assert _node_names(ast) == ["Declaration", "Declaration"]

    def test_function_declarator_with_params(self, c):
        ast = _parse("int f(void);\nint g(int a, char *b);\n", c)
        assert _node_names(ast) == ["Declaration", "Declaration"]

    def test_typedef_declaration(self, c):
        ast = _parse("typedef int myint;\n", c)
        assert _node_names(ast) == ["Declaration"]

    def test_parenthesized_declarator_recursion(self, c):
        """函数指针 `int (*fp)(int);` —— 声明符递归（括号声明符）的样本。"""
        ast = _parse("int (*fp)(int);\n", c)
        assert _node_names(ast) == ["Declaration"]

    def test_multiple_top_level_declarations(self, c):
        src = "int x;\nint *p;\nint a[10];\nint f(int a);\ntypedef int myint;\n"
        ast = _parse(src, c)
        assert _node_names(ast) == ["Declaration"] * 5


class TestArraySizeExpression:
    """数组长度从"只收数字字面量"放宽为**常量表达式**（阶段 2b 续）。

    语法层宽进——"是不是整型常量表达式"归语义层判；这里只断言**表达式进了 AST**。
    """

    def test_identifier_size(self, c):
        """`int a[N];` —— 宏/常量作长度（真实语料最常见）。"""
        ast = _parse("int a[N];\n", c)
        suffix = ast.sub_node[0].declarators.items[0].declarator.direct.suffixes.items[0]
        assert suffix.size.node_name == "Identifier"

    def test_constant_expression_size(self, c):
        """`int a[2 * 4];` —— 常量表达式作长度（优先级照样成立）。"""
        ast = _parse("int a[2 * 4];\n", c)
        suffix = ast.sub_node[0].declarators.items[0].declarator.direct.suffixes.items[0]
        assert suffix.size.node_name == "BinaryOp" and suffix.size.op == "*"

    def test_empty_size_still_ok(self, c):
        """`int a[];` —— 长度可省（不完整类型，语法允许）。"""
        ast = _parse("int a[];\n", c)
        assert _node_names(ast) == ["Declaration"]


class TestDeclarationRejection:
    """负样本：缺声明符 / 括号不闭合 / 悬空指针等必须被拒。"""

    @pytest.mark.parametrize(
        "src",
        [
            "int a[;\n",            # 数组括号不闭合
            "int f(int a,);\n",     # 参数表尾随逗号
            "int x\n",              # 缺分号
            "struct p { int a; \n",  # 成员体不闭合（阶段 2a）
        ],
    )
    def test_bad_source_reports(self, c_linter, src):
        errs = _lint(src, c_linter)
        assert errs, f"应报错但通过了：{src!r}"


class TestSyntaxWideIn:
    """语法层**宽进**的样本：C99 语法允许、但语义上非法的形态。

    ⚠ 这不是"漏检"而是**分层设计**：`declaration: declaration-specifiers
    init-declarator-list? ;` 里声明符列表**本身可选**（§6.7 语法）；
    "声明至少要声明一个声明符、一个标签或枚举成员"是**语义约束**（§6.7p2）。
    语法层宽进、语义层收（同 `float int x;` 的处理）——语义层检查属后续阶段
    （检查插件族），故此处**断言语法接受**，避免把语义判据塞进语法规则。
    """

    @pytest.mark.parametrize("src", ["int ;\n", "int ;\nint y;\n"])
    def test_declaration_without_declarator_is_syntactically_ok(self, c, src):
        ast = _parse(src, c)
        assert _node_names(ast), f"语法层应接受（语义约束归语义层）：{src!r}"

    def test_incomplete_declarator_fails_at_parse(self, c):
        """`int *;` —— 声明符不完整（`*` 后必须跟标识符或括号声明符）→ 解析层拒。

        ⚠ 断言在解析层：`Declarator` 要求 `@DirectDeclarator`，语法上不可能只有 `*`；
        而 linter 对"没能起始任何语句规则"的行会保持沉默（已知近似边界，
        见 `docs/gaps/gap-parser-linter-approximation.md`），不能拿它当语法判据。
        """
        assert _node_names(_parse("int *;\n", c)) == []


class TestStagingBoundaries:
    """阶段边界：明确本阶段**不**支持的面（防"看起来支持"）。"""

    def test_function_body_is_not_supported_yet(self, c_linter):
        """函数体属阶段 3（语句）——本阶段应被拒。"""
        assert _lint("int main(void) { return 0; }\n", c_linter)

    def test_struct_specifier_parses_after_stage_2a(self, c):
        """阶段 2a 起 `struct point p;` 是正常声明（原"静默跳过"行为随之后退场）。"""
        ast = _parse("struct point p;\n", c)
        assert _node_names(ast) == ["Declaration"]

    def test_specifier_combination_is_semantic_not_syntactic(self, c):
        """`float int x;` 语法层**宽进**（组合合法性归语义层）——应解析通过。

        这是**刻意的**：语法规则不表达"哪些说明符能共现"（那是语义），
        否则语法层会退化成类型系统。
        """
        ast = _parse("float int x;\n", c)
        assert _node_names(ast) == ["Declaration"]
