"""tests/engine/renderer/test_comment_ends_line.py — 行终止型注释判类（声明驱动）。

渲染阶段判断"行尾注释后必须换行"（否则同行后续元素回读时会被并入注释文本）
时，不得硬编码注释标点：词表来自语言包声明（`[comment] pairs` 的 kind，
经 `Lexer.line_terminating_comment_starts()` 传入），本测试固化该约束：
  - 传入声明词表 → 按词表判类（`//` 属、`/*` 不属）
  - 未传入（默认空）→ 一律判否（引擎自己不认识任何注释标点）
"""

from renderer.renderer import Renderer
from core.define import DEFAULT_RULES_DIR


def _renderer(starts: tuple[str, ...]) -> Renderer:
    return Renderer(DEFAULT_RULES_DIR, line_comment_starts=starts)


def test_declared_line_comment_ends_line() -> None:
    r = _renderer(("//",))
    assert r.comment_ends_line("// tail") is True
    assert r.comment_ends_line("  // 前导空白") is True


def test_block_comment_does_not_end_line() -> None:
    r = _renderer(("//",))
    assert r.comment_ends_line("/* block */") is False
    assert r.comment_ends_line("  /* block */") is False


def test_no_declaration_means_no_knowledge() -> None:
    """未传入声明 → 引擎不认识任何注释标点（零硬编码）。"""
    r = _renderer(())
    assert r.comment_ends_line("// tail") is False
    assert r.comment_ends_line("/* block */") is False


def test_vocabulary_comes_from_declaration() -> None:
    """词表完全由调用方声明（换成 `#` 也照样成立——引擎无语言知识）。"""
    r = _renderer(("#",))
    assert r.comment_ends_line("# yaml 注释") is True
    assert r.comment_ends_line("// not declared") is False
