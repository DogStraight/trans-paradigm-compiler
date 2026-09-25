"""tests/languages/c/test_c_declarations.py — C 包阶段 1：声明与声明符。

阶段 1 范围（`docs/gaps/gap-language-pack-scope.md`「C 语言包」）：词法 + 类型
说明符与**声明符**；**不含表达式与语句**（初始化器、函数体、数组长度表达式在
阶段 2/3）。故本文件的样本都是**外部声明序列**。

判据是**双向**的（阶段 0 定）：正样本必须进 AST（只测"不报错"会漏掉规则没接上），
负样本必须被拒（只测正样本会漏掉"语法过宽"）。

⚠ 说明符**组合合法性**（`long long int` 合法 / `float int` 非法）**不在语法层**判定
——语法层宽进、语义层收，故 `float int x;` 在本阶段**应当解析通过**，见
`test_specifier_combination_is_semantic_not_syntactic`。
"""

import pytest

from tests.languages.c.conftest import _lint, _node_names, _parse


_PARSE_BLOCKED = (
    "【已知阻塞】C 包的顶层 `Declaration` 解析不出节点（parse 报 match_length 0，"
    "AST 为空），而对照实验里 c4（`int a;` → VarDecl）与 yaml（`a: 1` → MappingEntry）"
    "的**顶层语句解析都正常**，故阻塞在解析层对声明规则形态的处理，不在本包的关键字/"
    "词法/token 类别（均已逐项核对）。已证伪的五个假设：①带括号 token 组 `(a|b)` "
    "②说明符规则层级过深 ③后缀规则组 `(@A|@B)*` ④首元素带量词组 `(x)*` "
    "⑤`@Identifier|@Rule` 交替。下一步（需新预算）：从**已知可用侧**二分——把 yaml "
    "`MappingEntry` 的最小形态（`production = [\"@Scalar|@MergeKey\", \"symbol.base.colon\"]`）"
    "复制进 C 包单规则最小包，逐项长成声明规则，定位是哪一项形态不被接受。"
)


@pytest.mark.xfail(strict=False, reason=_PARSE_BLOCKED)
class TestDeclarationParse:
    """正样本：声明进 AST，且声明符结构可查（**当前被解析层阻塞**，见 reason）。"""

    def test_single_declaration(self, c):
        ast = _parse("int x;\n", c)
        assert _node_names(ast) == ["Declaration"]
        decl = ast.sub_node[0]
        assert decl.declarators.first.direct.head.value.content == "x"

    def test_declaration_list(self, c):
        ast = _parse("int a, b, c;\n", c)
        decl = ast.sub_node[0]
        assert decl.declarators.first.direct.head.value.content == "a"
        assert decl.declarators.rest is not None

    def test_pointer_declarator(self, c):
        ast = _parse("int *p;\nchar **pp;\n", c)
        first, second = ast.sub_node
        assert first.declarators.first.pointers is not None
        assert second.declarators.first.direct.head.value.content == "pp"

    def test_specifier_order_is_free(self, c):
        """`const char *s;` 与 `char const *s;` 都应通过（顺序自由）。"""
        ast = _parse("const char *s;\nchar const *t;\n", c)
        assert _node_names(ast) == ["Declaration", "Declaration"]

    def test_multiword_type_specifier(self, c):
        ast = _parse("unsigned long long big;\n", c)
        spec = ast.sub_node[0].specs.first
        assert spec.first is not None and spec.rest is not None

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

    @pytest.mark.xfail(strict=False, reason=_PARSE_BLOCKED)
    def test_struct_specifier_is_not_supported_yet(self, c_linter):
        """struct/union/enum 说明符属阶段 2（类型）——本阶段应被拒。

        ⚠ 标 xfail：linter 对 `struct point p;` 当前**不报**诊断（`struct` 不在任何
        语句入口的 FIRST 集里 → 该行既不被解析也不被判错）。"阶段边界是否被正确
        拒绝"这类断言在解析阻塞下不可靠，故与正样本同批挂起——不要为了让测试变绿
        而放宽断言，那会把"静默接受未知语句"当成期望行为。
        """
        assert _lint("struct point p;\n", c_linter)

    @pytest.mark.xfail(strict=False, reason=_PARSE_BLOCKED)
    def test_specifier_combination_is_semantic_not_syntactic(self, c):
        """`float int x;` 语法层**宽进**（组合合法性归语义层）——应解析通过。

        这是**刻意的**：语法规则不表达"哪些说明符能共现"（那是语义），
        否则语法层会退化成类型系统。
        """
        ast = _parse("float int x;\n", c)
        assert _node_names(ast) == ["Declaration"]
