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
