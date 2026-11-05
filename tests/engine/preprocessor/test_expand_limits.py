"""宏展开预算超限必须发**可见信号**（审计小项，2026-11-05）。

既有边界：`[expand] max_iterations` 用尽时保留未展开文本（不崩、不猜）。此前是
**静默**停止——调用方看不出"没展开完"。现改为 `RuntimeWarning` + 保留原文：
判据 = 超限时能看见信号，且未展开文本原样保留。
"""

import re

import pytest

from lexer.comment_syntax import CommentSyntax
from preprocessor import _expand, macro_expand
from preprocessor.macro_shape import MacroCallArgs


def _call_args() -> MacroCallArgs:
    return MacroCallArgs(open="(", close=")", separator=",", nesting=(("(", ")"),))


def test_object_macro_budget_exhausted_warns():
    """对象宏重扫预算超限：可见告警 + 保留未展开宏名。"""
    with pytest.warns(RuntimeWarning, match="预算超限"):
        toks = macro_expand.expand_text_tokens(
            "A A", {"A": "1"}, {}, None, budget=1, prefix=""
        )
    assert "A" in macro_expand.join(toks)  # 第二个 A 因预算保留


def test_junction_budget_exhausted_warns(monkeypatch):
    """接缝重扫预算超限：可见告警 + 保留未展开接缝。"""
    monkeypatch.setattr(_expand, "_expand_cfg", {"max_iterations": 1})
    ctx = _expand._MacroExpandCtx(
        macro_re=re.compile(r"`([A-Za-z_]\w*)"),
        macro_defs={"g": "f", "f": "1"},
        func_macros={"g": ["a"], "f": ["a"]},
        call_args=_call_args(),
        suffix_re=None,
        policy=None,
        syntax=CommentSyntax(block_pairs=(), line_starts=()),
        lines=[],
    )
    body = macro_expand.tokenize("g")
    with pytest.warns(RuntimeWarning, match="预算超限"):
        toks, end = _expand._rescan_junction(ctx, body, "(9)(9)", 0, 1, 0)
    assert macro_expand.join(toks) == "f"  # 第二次接缝因预算保留
    assert end == 3  # 第一次接缝消费了 "(9)"
