"""tests/languages/c/test_c_control_flow.py — C 包阶段 3 Layer C：控制流语句。"""

import pytest

from tests.languages.c.conftest import _lint, _parse


def _body(src: str, c):
    """包进函数体，返回体内语句列表。"""
    ast = _parse(f"void f(void) {{ {src} }}\n", c)
    return ast.sub_node[0].body.body.items


def _names(items) -> list[str]:
    return [n.node_name for n in items]


def _unwrap(node):
    """剥掉内联选择器 / 可选位留下的 `seq` 包装层，返回其中的**规则**节点。

    ⚠ 引擎细节（实测）：`Stmt` 是 `inline = true` 的交替选择器，命中复合分支时结果会
    被套一层 `seq`；`(keyword.else,@Stmt)?` 这类**可选项**命中时同样套 `seq`，且 `seq`
    的子节点里**既有 token 节点（如 keyword.else）也有规则节点**。故解包要挑规则节点
    （node_name 不带 `keyword.` / `symbol.` / `bracket.` / `literal.` 前缀且非 `id`），
    不能取 `sub_node[0]`。测试只关心语义节点，避免把引擎包装形状写进断言。
    """
    name = getattr(node, "node_name", "")
    while name == "seq":
        children = getattr(node, "sub_node", None) or []
        rule_child = next((c for c in children if _is_rule(c)), None)
        if rule_child is None:
            break
        node, name = rule_child, rule_child.node_name
    return node


def _is_rule(node) -> bool:
    name = getattr(node, "node_name", "")
    return not name.startswith(
        ("keyword.", "symbol.", "bracket.", "literal.")
    ) and name != "id"


class TestIf:
    def test_if_without_else(self, c):
        items = _body("if (a) b;", c)
        assert _names(items) == ["IfStmt"]
        assert items[0].cond.node_name == "Identifier"
        assert items[0].then.node_name == "ExprStmt"

    def test_if_else(self, c):
        stmt = _body("if (a) b; else c;", c)[0]
        assert stmt.node_name == "IfStmt"
        assert getattr(stmt, "else_branch", None) is not None

    def test_if_else_with_blocks(self, c):
        stmt = _body("if (a) { x; } else { y; }", c)[0]
        assert _unwrap(stmt.then).node_name == "CompoundStmt"
        assert _unwrap(stmt.else_branch).node_name == "CompoundStmt"

    def test_condition_is_expression(self, c):
        stmt = _body("if (a && b) x;", c)[0]
        assert stmt.cond.node_name == "BinaryOp" and stmt.cond.op == "&&"


class TestLoops:
    def test_while(self, c):
        stmt = _body("while (a) x;", c)[0]
        assert stmt.node_name == "WhileStmt"
        assert stmt.body.node_name == "ExprStmt"

    def test_do_while(self, c):
        stmt = _body("do x; while (a);", c)[0]
        assert stmt.node_name == "DoWhileStmt"
        assert stmt.body.node_name == "ExprStmt"

    def test_for_with_all_parts(self, c):
        stmt = _body("for (i = 0; i < n; i++) x;", c)[0]
        assert stmt.node_name == "ForStmt"
        assert stmt.init.node_name == "BinaryOp" and stmt.init.op == "="
        assert stmt.cond.node_name == "BinaryOp" and stmt.cond.op == "<"
        assert stmt.step.node_name == "UnaryOp" and stmt.step.position == "postfix"

    def test_for_with_empty_parts(self, c):
        """`for (;;) x;` —— 三段都可省（C99 语法允许），是可选的**合法**形态。"""
        stmt = _body("for (;;) x;", c)[0]
        assert stmt.node_name == "ForStmt"


class TestSwitch:
    def test_switch_with_case_and_default(self, c):
        stmt = _body("switch (a) { case 1: x; break; default: y; }", c)[0]
        assert stmt.node_name == "SwitchStmt"
        body = stmt.body
        assert body.node_name == "CompoundStmt"
        assert _names(body.body.items) == [
            "CaseLabel",
            "ExprStmt",
            "BreakStmt",
            "DefaultLabel",
            "ExprStmt",
        ]

    def test_case_value_is_expression(self, c):
        stmt = _body("switch (a) { case 1 + 2: x; }", c)[0]
        assert stmt.body.body.items[0].value.node_name == "BinaryOp"


class TestJumps:
    def test_break(self, c):
        assert _names(_body("while (a) break;", c)) == ["WhileStmt"]

    def test_continue(self, c):
        stmt = _body("while (a) continue;", c)[0]
        assert stmt.body.node_name == "ContinueStmt"

    def test_goto_and_label(self, c):
        items = _body("goto done; done: x;", c)
        assert _names(items) == ["GotoStmt", "LabelStmt"]
        assert items[0].label.content == "done"
        assert items[1].name.content == "done"

    def test_nested_control_flow(self, c):
        items = _body("while (a) { if (b) continue; else break; }", c)
        inner = items[0].body.body.items
        assert _names(inner) == ["IfStmt"]


class TestControlFlowRejection:
    @pytest.mark.parametrize(
        "src",
        [
            "if (a b;",            # 条件括号不闭合
            "while a) x;",         # 缺左括号
            "do x;",               # do 缺 while
            "switch (a) { case : x; }",  # case 缺值
        ],
    )
    def test_bad_control_flow_reports(self, c_linter, src):
        assert _lint(f"void f(void) {{ {src} }}\n", c_linter), f"应报错但通过了：{src!r}"

    def test_for_with_decl_init(self, c):
        """`for (int i = 0; …)` —— 声明式初值（C99 §6.8.5.3），阶段 2b 起支持。

        ⚠ 本用例原为**边界测试**（断言"报错"），阶段 2b 落地后**转正**为结构性断言：
        边界测试必须随能力落地退场——否则它会靠 linter 的近似误报继续"绿"，
        变成假绿（本轮实测：能力已支持，但旧断言仍通过，因为 linter 对该形态本就误报）。
        """
        stmt = _body("for (int i = 0; i < n; i++) x;", c)[0]
        assert stmt.node_name == "ForStmt"
        assert stmt.init.node_name == "ForInitDecl"
        assert stmt.cond.node_name == "BinaryOp" and stmt.cond.op == "<"

    def test_for_with_expression_init_still_works(self, c):
        """表达式初值形态不受影响（`for (i = 0; …)`）。"""
        stmt = _body("for (i = 0; i < n; i++) x;", c)[0]
        assert stmt.node_name == "ForStmt"
        assert stmt.init.node_name == "BinaryOp" and stmt.init.op == "="
