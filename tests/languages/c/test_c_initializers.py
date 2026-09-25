"""tests/languages/c/test_c_initializers.py — C 包阶段 2b：初始化器。

C99 §6.7.8：`= assignment-expression` 或 `= { initializer-list }`（可递归嵌套）。
由 `grammar/c/01_declarations.toml` 的 `InitDeclarator` / `Initializer` / `InitList` 承担。

判据双向：正样本断言 `init` **真的挂上了且是预期节点**（可选位点最容易假绿——本包
阶段 2a 吃过"可选位点掩盖失效"的教训）；负样本走**解析层**（linter 对残缺初始化器
沉默，属已知近似边界，拿它当语法判据会假绿）。
"""

import pytest

from core.define import iter_nodes

from tests.languages.c.conftest import _parse


def _is_rule(node) -> bool:
    name = getattr(node, "node_name", "")
    return not name.startswith(
        ("keyword.", "symbol.", "bracket.", "literal.")
    ) and name != "id"


def _unwrap(node):
    """剥掉 `seq` 包装，返回其中的**规则**节点。

    ⚠ 引擎细节：`(equal,@Initializer)?` 是**可选组**，命中时结果被套一层 `seq`
    （子节点含 `=` 这个 token 与真正的初始化器节点）；`Initializer` 又是 `inline = true`
    （不产生自己的节点）。故取初始化器要"剥 seq + 挑规则节点"，不能直接 `.value`。
    """
    name = getattr(node, "node_name", "")
    while name == "seq":
        children = getattr(node, "sub_node", None) or []
        rule_child = next((c for c in children if _is_rule(c)), None)
        if rule_child is None:
            break
        node, name = rule_child, rule_child.node_name
    return node


def _first_decl(src: str, c):
    return _parse(src, c).sub_node[0]


def _init(src: str, c):
    """第一条声明的第一个声明符的初始化器（未挂载 → None），已剥 seq/inline 层。"""
    raw = getattr(_first_decl(src, c).declarators.items[0], "init", None)
    return None if raw is None else _unwrap(raw)


def _count(node, name: str) -> int:
    return sum(1 for n in iter_nodes(node) if n.node_name == name)


class TestScalarInitializer:
    def test_int_with_literal(self, c):
        init = _init("int x = 1;\n", c)
        assert init is not None, "初始化器未挂载（可选位点静默为空）"
        assert init.node_name == "Number"

    def test_initializer_is_full_expression(self, c):
        """`= a + b * c` —— 初始化器是表达式（优先级照样成立）。"""
        init = _init("int x = a + b * c;\n", c)
        assert init.node_name == "BinaryOp" and init.op == "+"
        assert init.right.node_name == "BinaryOp" and init.right.op == "*"

    def test_string_initializer(self, c):
        assert _init('char *s = "hi";\n', c).node_name == "StringLiteral"

    def test_call_initializer(self, c):
        assert _init("int x = f(a);\n", c).node_name == "CallExpr"

    def test_multiple_declarators_with_and_without_init(self, c):
        """`int i = 0, j;` —— 逐个声明符各自可选带初始化器（第二个为空）。"""
        decl = _first_decl("int i = 0, j;\n", c)
        assert getattr(decl.declarators.items[0], "init", None) is not None
        rest = decl.declarators.items[1:]
        assert rest, "第二个声明符没进 AST"
        second = _unwrap(rest[0].sub_node[1]) if _is_rule(rest[0]) is False else rest[0]
        assert getattr(second, "init", None) is None


class TestListInitializer:
    def test_array_initializer_list(self, c):
        init = _init("int a[3] = {1, 2, 3};\n", c)
        assert init.node_name == "InitList"
        assert _count(init, "Number") == 3, "初始化列表元素数不对"

    def test_empty_initializer_list(self, c):
        """`= {}` —— 空初始化列表。"""
        init = _init("int a[3] = {};\n", c)
        assert init.node_name == "InitList"
        assert _count(init, "Number") == 0

    def test_trailing_comma(self, c):
        init = _init("int a[2] = {1, 2,};\n", c)
        assert init.node_name == "InitList"
        assert _count(init, "Number") == 2

    def test_nested_initializer_list(self, c):
        """`= {{1}, {2}}` —— 嵌套初始化列表（结构体数组 / 二维数组的写法）。"""
        init = _init("int m[2][1] = {{1}, {2}};\n", c)
        assert init.node_name == "InitList"
        assert _count(init, "InitList") >= 2, "嵌套的内层 InitList 没进 AST"
        assert _count(init, "Number") == 2

    def test_initializer_list_of_expressions(self, c):
        """列表元素是完整表达式（`{a + 1, b * 2}`）。"""
        init = _init("int a[2] = {x + 1, y * 2};\n", c)
        assert _count(init, "BinaryOp") == 2


class TestInitializerRejection:
    """负样本走**解析层**：linter 对残缺初始化器沉默（已知近似边界），不能当语法判据。"""

    @pytest.mark.parametrize(
        "src",
        [
            "int x = ;\n",           # 缺初始化表达式
            "int a[2] = {1,\n",      # 初始化列表不闭合
            "int a[2] = {1, 2\n",    # 列表缺右花括号
        ],
    )
    def test_bad_initializer_fails_at_parse(self, c, src):
        ast = _parse(src, c)
        names = [n.node_name for n in (getattr(ast, "sub_node", []) or [])]
        assert names == [], f"应解析失败但产出了顶层节点 {names}"


class TestDesignatedInitializers:
    """C99 §6.7.8 指示符初始化：`.field = v` / `[i] = v`，可链。"""

    def test_member_designator(self, c):
        init = _init("struct s x = {.a = 1};\n", c)
        assert init.node_name == "InitList"
        assert _count(init, "DesignatedInitializer") == 1
        assert _count(init, "MemberDesignator") == 1
        assert _count(init, "Number") == 1

    def test_index_designator(self, c):
        init = _init("int a[5] = {[0] = 1, [4] = 2};\n", c)
        assert _count(init, "DesignatedInitializer") == 2
        assert _count(init, "IndexDesignator") == 2
        assert _count(init, "Number") == 4  # 两个下标 + 两个值

    def test_chained_designator(self, c):
        """`.a.b = 1` —— 指示符可链（designator+）。"""
        init = _init("struct s x = {.a.b = 1};\n", c)
        assert _count(init, "MemberDesignator") == 2

    def test_mixed_designated_and_plain(self, c):
        """混用：`{1, .b = 2}` —— 真实代码里的常见写法。"""
        init = _init("struct s x = {1, .b = 2};\n", c)
        assert _count(init, "DesignatedInitializer") == 1
        assert _count(init, "Number") == 2

    def test_designator_index_is_expression(self, c):
        """下标是常量表达式（语法层宽进）。"""
        init = _init("int a[4] = {[1 + 1] = 9};\n", c)
        assert _count(init, "IndexDesignator") == 1
        assert _count(init, "BinaryOp") == 1

    @pytest.mark.parametrize(
        "src",
        [
            "struct s x = {.a 1};\n",     # 指示符缺 `=`
            "int a[2] = {[0] 1};\n",       # 同上（下标形态）
            "int a[2] = {[0 = 1};\n",      # 下标缺 `]`
        ],
    )
    def test_bad_designator_fails_at_parse(self, c, src):
        ast = _parse(src, c)
        names = [n.node_name for n in (getattr(ast, "sub_node", []) or [])]
        assert names == [], f"应解析失败但产出了顶层节点 {names}"
