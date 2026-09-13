"""空体宏 → 占位 token。

空体宏展开为空（`` `TV80DELAY ``：`rd_n <= `TV80DELAY 1'b1;` ≡ `rd_n <= 1'b1;`）：
在解析流里它不该顶替任何语法元素，只该被**跳过**——换成 trivia 类占位 token
（内容保留调用原文供渲染回插）。非空体宏不动，留给通配协议。

Doc: core/token_protocol.py（`macro.placeholder` 协议常量与 trivia 集合）
"""
import pytest

from core.token_protocol import (
    MACRO_CALL_TOKEN_TYPE,
    PLACEHOLDER_TOKEN_TYPE,
    TRIVIA_TOKEN_TYPES,
)
from lexer import Lexer
from pipeline import _stage_macro_placeholders

pytestmark = pytest.mark.usefixtures("config_loaded")


def _tokens(src: str) -> list:
    return Lexer(rules_dir="grammar/verilog").tokenize(src)


def test_placeholder_type_is_trivia() -> None:
    """占位 token 是引擎协议里的 trivia（parser/linter 跳过）。"""
    assert PLACEHOLDER_TOKEN_TYPE in TRIVIA_TOKEN_TYPES


def test_empty_body_macro_becomes_placeholder() -> None:
    """空体宏（体为空串）→ 占位 token，内容保留调用原文。"""
    toks = _tokens("module m;\n  assign a = `TV80DELAY 1'b1;\nendmodule\n")
    assert any(t.type == MACRO_CALL_TOKEN_TYPE for t in toks)
    _stage_macro_placeholders(toks, {"TV80DELAY": ""})
    ph = [t for t in toks if t.type == PLACEHOLDER_TOKEN_TYPE]
    assert len(ph) == 1
    assert ph[0].content == "`TV80DELAY"


def test_whitespace_only_body_is_empty() -> None:
    """只有空白的宏体同样算空体（`\\`define X \\n` 形态）。"""
    toks = _tokens("module m;\n  assign a = `NOOP 1'b1;\nendmodule\n")
    _stage_macro_placeholders(toks, {"NOOP": "  "})
    assert any(t.type == PLACEHOLDER_TOKEN_TYPE for t in toks)


def test_nonempty_body_macro_untouched() -> None:
    """非空体宏不动（交给通配协议），未知宏也不动。"""
    toks = _tokens("module m;\n  assign a = `W b;\nendmodule\n")
    _stage_macro_placeholders(toks, {"W": "8", "OTHER": ""})
    assert not any(t.type == PLACEHOLDER_TOKEN_TYPE for t in toks)
    assert any(t.type == MACRO_CALL_TOKEN_TYPE for t in toks)


def test_stage_noop_without_table() -> None:
    """宏表为空（未开宏处理）→ 直接返回，无副作用。"""
    toks = _tokens("module m;\n  assign a = `TV80DELAY 1'b1;\nendmodule\n")
    before = [t.type for t in toks]
    _stage_macro_placeholders(toks, {})
    assert [t.type for t in toks] == before
