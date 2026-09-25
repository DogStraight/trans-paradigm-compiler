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
        assert decl.declarators.first.direct.head.content == "x"

    def test_declaration_list(self, c):
        ast = _parse("int a, b, c;\n", c)
        decl = ast.sub_node[0]
        assert decl.declarators.first.direct.head.content == "a"
        assert len(decl.declarators.rest.items) == 2  # b, c

    def test_pointer_declarator(self, c):
        ast = _parse("int *p;\nchar **pp;\n", c)
        first, second = ast.sub_node
        assert first.declarators.first.pointers.node_name == "Pointer"
        assert second.declarators.first.direct.head.content == "pp"

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


class TestDeclarationRejection:
    """负样本：缺声明符 / 括号不闭合 / 悬空指针等必须被拒。"""

    @pytest.mark.parametrize(
        "src",
        [
            "int ;\n",              # 缺声明符
            "int *;\n",             # 只有指针
            "int a[;\n",            # 数组括号不闭合
            "int f(int a,);\n",     # 参数表尾随逗号
            "int x\n",              # 缺分号
            "int ;\nint y;\n",     # 首个声明即缺声明符
        ],
    )
    def test_bad_source_reports(self, c_linter, src):
        errs = _lint(src, c_linter)
        assert errs, f"应报错但通过了：{src!r}"


class TestStagingBoundaries:
    """阶段边界：明确本阶段**不**支持的面（防"看起来支持"）。"""

    def test_initializer_is_not_supported_yet(self, c_linter):
        """初始化器 `= expr` 属阶段 3（表达式）——本阶段应被拒，不得静默接受。"""
        assert _lint("int x = 1;\n", c_linter)

    def test_function_body_is_not_supported_yet(self, c_linter):
        """函数体属阶段 3（语句）——本阶段应被拒。"""
        assert _lint("int main(void) { return 0; }\n", c_linter)

    def test_struct_specifier_is_currently_skipped_silently(self, c_linter):
        """`struct point p;` 本阶段**既不解析也不报错**（记录现状，非期望）。

        ⚠ 这是 **linter 近似**的已知边界（不是本包的阶段设计）：语句发现按"首 token
        能起始某条语句规则"挑选候选，`struct` 在本阶段不属于任何语句入口的 FIRST 集
        → 该行被整体跳过，既不解析也不诊断（对比 `int x` 缺分号会报错，因为 `int`
        是语句入口）。阶段 2 加入 struct/union/enum 说明符后，此行为自然改变——
        届时本用例应改为断言"被拒"或"被接受"，不要保留"静默跳过"作为期望。
        """
        assert _lint("struct point p;\n", c_linter) == []

    def test_specifier_combination_is_semantic_not_syntactic(self, c):
        """`float int x;` 语法层**宽进**（组合合法性归语义层）——应解析通过。

        这是**刻意的**：语法规则不表达"哪些说明符能共现"（那是语义），
        否则语法层会退化成类型系统。
        """
        ast = _parse("float int x;\n", c)
        assert _node_names(ast) == ["Declaration"]
