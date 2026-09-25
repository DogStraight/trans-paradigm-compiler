"""tests/languages/c/test_c_types.py — C 包阶段 2a：类型说明符（struct/union/enum/typedef 名）。

范围见 `grammar/c/02_types.toml` 头注与 `docs/gaps/gap-language-pack-scope.md`。
判据双向：正样本进 AST（结构与成员/枚举项可查），负样本被拒。

⚠ 两条**刻意留给语义层**的歧义（本文件不把它们当语法判据）：
  1. `int ;` 语法合法（§6.7 声明符列表可选），"至少声明一个声明符/标签/枚举项"
     是语义约束（§6.7p2）；
  2. 标识符开头的语句既可能是声明（`myint x;`）也可能是表达式语句（`x = 1;`）——
     C 靠符号表消歧，本包同样留给语义层（阶段 3 接表达式语句时必须处理）。
"""

import pytest

from tests.languages.c.conftest import _lint, _node_names, _parse


class TestStructUnion:
    def test_tagged_struct_declaration(self, c):
        ast = _parse("struct point p;\n", c)
        assert _node_names(ast) == ["Declaration"]
        spec = ast.sub_node[0].specs.spec
        assert spec.node_name == "StructSpecifier"
        assert spec.tag.content == "point"

    def test_struct_with_body(self, c):
        ast = _parse("struct point { int x; int y; };\n", c)
        assert _node_names(ast) == ["Declaration"]
        spec = ast.sub_node[0].specs.spec
        assert len(spec.body.members.items) == 2

    def test_struct_with_body_and_declarator(self, c):
        ast = _parse("struct point { int x; } p;\n", c)
        decl = ast.sub_node[0]
        assert decl.specs.spec.tag.content == "point"

    def test_anonymous_struct(self, c):
        """匿名结构体（`typedef struct { … } T;` 的常见写法）必须有成员体。"""
        ast = _parse("struct { int x; } anon;\n", c)
        spec = ast.sub_node[0].specs.spec
        assert spec.node_name == "AnonStructSpecifier"

    def test_union(self, c):
        ast = _parse("union value { int i; float f; };\n", c)
        spec = ast.sub_node[0].specs.spec
        assert spec.node_name == "StructSpecifier"
        assert spec.kind.node_name == "StructOrUnion"

    def test_typedef_anonymous_struct(self, c):
        """`typedef struct { … } T;` —— 真实 C 语料里最常见的用法。"""
        ast = _parse("typedef struct { int x; } T;\n", c)
        assert _node_names(ast) == ["Declaration"]


class TestEnum:
    def test_enum_with_values(self, c):
        ast = _parse("enum color { RED, GREEN = 2, BLUE };\n", c)
        body = ast.sub_node[0].specs.spec.body
        assert body.first.name.content == "RED"
        assert len(body.rest.items) == 2

    def test_enum_tagged_only(self, c):
        ast = _parse("enum color c;\n", c)
        assert ast.sub_node[0].specs.spec.tag.content == "color"

    def test_anonymous_enum(self, c):
        ast = _parse("enum { A, B } e;\n", c)
        assert ast.sub_node[0].specs.spec.node_name == "AnonEnumSpecifier"


class TestTypedefNameAsType:
    def test_typedef_name_first_specifier(self, c):
        """`myint x;` —— 标识符作类型（语法层宽进，是否真是 typedef 名归语义层）。"""
        ast = _parse("myint x;\n", c)
        assert _node_names(ast) == ["Declaration"]

    def test_typedef_name_does_not_eat_declarator(self, c):
        """⚠ 回归守卫：typedef 名**只允许在首个说明符位置**——否则贪婪的说明符重复项
        会把声明符名当类型名吃掉（实测曾发生：`int x;` 解析成无声明符）。
        """
        ast = _parse("int x;\n", c)
        decl = ast.sub_node[0]
        assert decl.declarators.first.declarator.direct.head.content == "x"


class TestTypesRejection:
    @pytest.mark.parametrize(
        "src",
        [
            "struct point { int x; \n",      # 成员体不闭合
            "enum color { RED, \n",         # 枚举体不闭合
        ],
    )
    def test_bad_type_source_reports(self, c_linter, src):
        assert _lint(src, c_linter), f"应报错但通过了：{src!r}"

    def test_member_without_declarator_fails_at_parse(self, c):
        """成员缺声明符（`struct p { int ; };`）在**解析层**被拒。

        ⚠ 断言放在解析层而非 linter：`StructMember` 要求声明符列表非空，故语法上
        不可能匹配；而 linter 对"成员体不平衡"的整行会走近似路径（不报），
        那是已知的 linter 近似边界（见 `docs/gaps/gap-parser-linter-approximation.md`），
        不能拿它当语法判据。
        """
        assert _node_names(_parse("struct point { int ; };\n", c)) == []
