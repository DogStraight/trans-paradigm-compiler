"""parser/_comment_trivia.py 单测——注释琐碎判定的单点实现。

收敛前同一判定有三处实现（`_production._starts_line` /
`_production._is_line_only_comment` / `pratt_parser._is_own_line`），
且 `space` 子类型匹配范围与"是否跳过注释"语义不一致（同一输入可因路径
不同得到不同分类）。本测试把三种判定的边界钉在共享实现上。
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

from core.define import Token  # noqa: E402
from parser._comment_trivia import (  # noqa: E402
    comment_leave_to_expression,
    is_line_only,
    is_midline,
    prev_significant_index,
)


def _tokens(*specs):
    """specs: (type, content, line) 三元组序列 → Token 列表。"""
    return [Token(content=c, type=ty, line=ln) for ty, c, ln in specs]


def test_prev_significant_skips_space_namespace_and_comments():
    """`space.*` 全子类型（含 space.indent/space.dedent）+ 换行 + 注释都跳过。"""
    toks = _tokens(
        ("keyword.wire", "wire", 1),
        ("space.indent", "    ", 1),
        ("id", "a", 1),
        ("newline", "\n", 1),
        ("space.fold", "    ", 2),
        ("comment", "// c1", 2),
        ("newline", "\n", 2),
        ("space.dedent", "", 3),
        ("comment", "// c2", 3),
    )
    assert prev_significant_index(toks, 8) == 2  # c2 之前是 a（跨 space/换行/注释）


def test_prev_significant_none_at_head():
    toks = _tokens(("newline", "\n", 1), ("comment", "// c", 2))
    assert prev_significant_index(toks, 1) == -1


def test_is_line_only_across_comment_line():
    """独占行：前一显著 token 在更早的行（中间隔着注释行也算）。"""
    toks = _tokens(
        ("id", "a", 1),
        ("newline", "\n", 1),
        ("comment", "// c1", 2),
        ("newline", "\n", 2),
        ("comment", "// c2", 3),
    )
    assert is_line_only(toks, 4) is True


def test_is_line_only_false_when_code_precedes_on_same_line():
    toks = _tokens(("id", "a", 1), ("space", " ", 1), ("comment", "// c", 1))
    assert is_line_only(toks, 2) is False


def test_is_line_only_true_at_file_head():
    toks = _tokens(("comment", "// c", 1), ("newline", "\n", 1))
    assert is_line_only(toks, 0) is True


def test_is_midline_code_after_comment_on_same_line():
    toks = _tokens(
        ("id", "a", 1), ("space", " ", 1), ("comment", "/* c */", 1),
        ("space", " ", 1), ("id", "b", 1), ("newline", "\n", 1),
    )
    assert is_midline(toks, 2) is True


def test_is_midline_false_when_next_code_is_next_line():
    toks = _tokens(
        ("id", "a", 1), ("comment", "// c", 1),
        ("newline", "\n", 1), ("space.fold", "    ", 2), ("id", "b", 2),
    )
    assert is_midline(toks, 1) is False


def test_is_midline_false_at_tail():
    toks = _tokens(("comment", "// c", 1), ("newline", "\n", 1))
    assert is_midline(toks, 0) is False


# ── 路由判据：让位闸门 `comment_leave_to_expression` ──


def _wire_like_tokens():
    """`wire a =\n// c\n(expr)` 形状：`=` 已匹配、注释后换行接右操作数。"""
    return _tokens(
        ("id", "a", 1),
        ("space", " ", 1),
        ("symbol.base.equal", "=", 1),
        ("newline", "\n", 1),
        ("space.fold", "    ", 2),
        ("comment", "// c", 2),
        ("newline", "\n", 2),
        ("bracket.l_parentheses", "(", 3),
    )


def test_leave_to_expression_accepts_rule_interior_comment():
    """规则内部（本产生式已匹配 `=`、锚在规则起点之后）→ 让位。"""
    toks = _wire_like_tokens()
    assert comment_leave_to_expression(toks, 5, production_pointer=1, production_start_ptr=2) is True


def test_leave_to_expression_rejects_first_element():
    """`production_pointer == 0`（项首元素前 = 列表项间）→ 不让位（容器上浮）。"""
    toks = _wire_like_tokens()
    assert comment_leave_to_expression(toks, 5, production_pointer=0, production_start_ptr=2) is False


def test_leave_to_expression_rejects_anchor_before_rule_start():
    """锚属上一项（下标 < 规则起点）→ 不让位。"""
    toks = _wire_like_tokens()
    assert comment_leave_to_expression(toks, 5, production_pointer=1, production_start_ptr=9) is False


def test_leave_to_expression_rejects_midline_comment():
    """行中注释（同行前后均有代码）→ 不让位（走 inline_after 行内原位）。"""
    toks = _tokens(
        ("id", "a", 1), ("space", " ", 1), ("comment", "/* c */", 1),
        ("space", " ", 1), ("id", "b", 1),
    )
    assert comment_leave_to_expression(toks, 2, production_pointer=1, production_start_ptr=0) is False


class TestParseContextSnapshot:
    """缺口 b：产生式位置状态（元素序号 / 规则匹配起点）必须在回溯快照里。

    两者供注释让位闸门判据使用；回溯不还原会让闸门读到旧规则的位置状态
    （已经踩过一次同类坑：`current_rule` 退出不还原 → 闸门读到内层 inline
    规则的旧值）。
    """

    def test_snapshot_round_trip_restores_production_fields(self):
        from parser.parser_core import ParseContext

        ctx = ParseContext(tokens=[])
        ctx.production_pointer = 3
        ctx.production_start_ptr = 7
        snapshot = ctx.create_snapshot()
        ctx.production_pointer = 0
        ctx.production_start_ptr = 0
        ctx.restore_snapshot(snapshot)
        assert ctx.production_pointer == 3
        assert ctx.production_start_ptr == 7
