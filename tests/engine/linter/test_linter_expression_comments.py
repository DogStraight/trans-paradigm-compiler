"""linter 表达式注释回退：注释是 trivia，不得让 pratt 误报（C 语料 crc32 形态）。

宏体尾注释被铺进流后位于三元 `?:` 中间（`b & 1 ? x /* c */ : y`）；pratt 只跳
space/newline ⇒ 停在 comment/抛"意外 token"。表达式检查器在此时用缓存滤注释视图
重试（`linter/checkers/expression.py::_comment_fallback`）。
"""

from __future__ import annotations

import os

from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from linter.scanner import LinterScanner

_PACK = "grammar/c"
_PLUGINS = os.path.join(_PACK, "plugins")


def _scanner() -> LinterScanner:
    ConfigRegistry.load_language(_PACK, plugins_dir=_PLUGINS)
    return LinterScanner(
        rules_dir=_PACK, register=GrammarRulesRegister(), ext_dirs=[_PLUGINS]
    )


def test_ternary_comment_not_reported() -> None:
    scanner = _scanner()
    src = "void f(void){ b = b & 1 ? (b >> 1) ^ 0xed /* c */ : b >> 1; }\n"
    assert [e for e in scanner.scan(src) if e.blocking] == []


def test_ternary_comment_in_loop_body_not_reported() -> None:
    scanner = _scanner()
    src = "void f(void){ for(;;){ b = b & 1 ? (b >> 1) ^ 0xed /* c */ : b >> 1; } }\n"
    assert [e for e in scanner.scan(src) if e.blocking] == []
