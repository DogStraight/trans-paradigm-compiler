"""generate 条件求值面（`[structure]` 声明驱动）——纯单元测试。

组别归属：analyzer（结构提取/elaboration 协议声明面）——`test_verilog_pack_declares_gen_face`
标 smoke，守"语言包必须声明该面"，避免声明缺失静默退化为不过滤。

覆盖三点：
1. 形态全走声明（逻辑非前缀 / 分支规则名 / 条件·then·else 字段名）；
2. 未声明 → 保守退让（不认取反 = 不可判；不认 generate 块 = 不过滤）；
3. 声明类型非法 → `gen_face()` 直接报错（配置加载点 fail-fast）。
"""

from __future__ import annotations

import pytest

from core.define import Node

from analyzer.structure import GenerateEvaluator, StructureCtx

_FACE = {
    "gen_block_rule": "GenBlock",
    "gen_branch_rules": ["IfB", "ElsIf"],
    "gen_not_ops": ["!"],
    "fields": {
        "gen_condition": "cond",
        "gen_then": "then_b",
        "gen_else_chain": "els",
    },
}


class _FakeRenderer:
    """渲染替身：不碰真语言包，直接给固定文本（条件求值只吃文本）。"""

    def __init__(self, text: str) -> None:
        self.text = text

    def render(self, node) -> str:
        del node  # 替身不消费入参
        return self.text


def _ctx(struct: dict, render_text: str = "") -> StructureCtx:
    ctx = StructureCtx(
        rules_dir="grammar/verilog",
        ext_dirs=[],
        include_dirs=[],
        expand_macros=False,
        ensure_shared=lambda: {"renderer": _FakeRenderer(render_text)},
    )
    ctx.struct = struct
    ctx.fields = struct.get("fields") or {}
    return ctx


def _if_node(field: str = "cond") -> Node:
    """带条件字段的分支节点替身（字段名由声明给出，故这里也按声明挂）。"""
    node = Node("IfB")
    node.add_attr(field, Node("Identifier"))
    return node


def _eval(struct: dict, text: str, params: dict):
    ctx = _ctx(struct, text)
    return GenerateEvaluator(ctx)._eval_gen_cond(_if_node(), params, ctx.gen_face())


@pytest.mark.smoke
def test_verilog_pack_declares_gen_face():
    """语言包必须声明 generate 条件面——缺声明会静默退化为"不过滤"（漏过滤 → 误报）。"""
    from analyzer.checker import ProjectChecker

    checker = ProjectChecker(rules_dir="grammar/verilog")
    checker._prepare_run([])  # 归一化 + 加载语言包 + refresh（含声明校验）
    face = checker._ctx.gen_face()
    assert face.block_rule, "[structure] gen_block_rule 未声明"
    assert face.branch_rules, "[structure] gen_branch_rules 未声明"
    assert face.not_ops, "[structure] gen_not_ops 未声明"
    assert face.condition_field and face.then_field and face.else_field


def test_literal_and_plain_param_truth():
    assert _eval(_FACE, "0", {}) is False
    assert _eval(_FACE, "3", {}) is True
    assert _eval(_FACE, "W", {"W": "1"}) is True
    assert _eval(_FACE, "W", {"W": "0"}) is False
    # 参数值非纯数字 → 不可判（保守）
    assert _eval(_FACE, "W", {"W": "DATA_W"}) is None


def test_not_op_declared_negates_param():
    """`!参数名` 的取反语义来自声明（引擎不认识 `!` 这个拼写）。"""
    assert _eval(_FACE, "!W", {"W": "0"}) is True
    assert _eval(_FACE, "!W", {"W": "5"}) is False
    # 前缀与名字之间允许空白（渲染文本可能带空格）
    assert _eval(_FACE, "! W", {"W": "0"}) is True
    # 参数值非纯数字 → 不可判
    assert _eval(_FACE, "!W", {"W": "DATA_W"}) is None


def test_not_op_undeclared_is_undecidable():
    """未声明逻辑非前缀 → 不认取反，落兜底（不可判），不猜语言语义。"""
    struct = {k: v for k, v in _FACE.items() if k != "gen_not_ops"}
    assert _eval(struct, "!W", {"W": "0"}) is None


def test_not_op_declared_by_language_not_hardcoded():
    """换个语言声明别的取反拼写 → 引擎照认（证明不是硬编码 `!`）。"""
    struct = {**_FACE, "gen_not_ops": ["not "]}
    assert _eval(struct, "not W", {"W": "0"}) is True
    assert _eval(struct, "!W", {"W": "0"}) is None


def test_condition_field_comes_from_declaration():
    """条件字段名走声明：换字段名后按旧名取不到 → 不可判。"""
    struct = {**_FACE, "fields": {**_FACE["fields"], "gen_condition": "other"}}
    assert _eval(struct, "0", {}) is None


def test_undeclared_block_rule_means_no_filtering():
    """未声明 generate 块规则 → 空活性表（调用方按"全部 active"处理，保守）。"""
    ctx = _ctx({"fields": {}})
    face = ctx.gen_face()
    assert face.block_rule == "" and face.branch_rules == ()

    class _Fr:
        ast = Node("Root")

    assert GenerateEvaluator(ctx)._precompute_generate_active(_Fr()) == {}


@pytest.mark.parametrize(
    "struct",
    [
        {"gen_not_ops": "!"},  # 须为列表
        {"gen_not_ops": [" ", ""]},  # 元素须非空字符串
        {"gen_branch_rules": ["IfB", 1]},  # 元素须字符串
        {"gen_branch_rules": "IfB"},  # 须为列表
    ],
)
def test_malformed_declaration_fails_fast(struct: dict):
    with pytest.raises(ValueError):
        _ctx(struct).gen_face()
