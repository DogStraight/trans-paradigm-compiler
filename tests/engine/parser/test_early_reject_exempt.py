"""FIRST 早拒的开放式豁免判据：任意 `macro.<name>` 不得被误拒。

宏观 token 名由语言包/指令名生成（开放集）；早拒表若只列 `macro.call`，
后加宏指令会被当成"不可能起始该规则"而误拒。本测试锁前缀判据。
"""

from __future__ import annotations

from types import SimpleNamespace

from parser._production import _early_reject_exempt


def test_macro_prefix_is_exempt() -> None:
    parser = SimpleNamespace(_first_reject_special={"space.indent"})
    assert _early_reject_exempt(parser, "macro.call")
    assert _early_reject_exempt(parser, "macro.ifdef")
    assert _early_reject_exempt(parser, "macro.any_new_directive")


def test_skip_type_and_ordinary_token() -> None:
    parser = SimpleNamespace(_first_reject_special={"space.indent"})
    assert _early_reject_exempt(parser, "space.indent")
    assert not _early_reject_exempt(parser, "id")
