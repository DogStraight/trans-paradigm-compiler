"""宏调用后随字面量后缀的形态模式（语言包 `[macro_recognition]` 的 `suffix_after_call`）。

```
[macro_recognition]
suffix_after_call = "'[sS]?[bBoOdDhH]?[0-9a-fA-FxXzZ_?]*"
```

- 该模式把 `` `W'd0 `` 的后缀一并纳入**调用区间**，使替换结果与 token 边界对齐
  （还原按 token 区间回插宏调用原文，ADR-0017 决策 3/4）；
- 比 `[[number.based]]` 宽一档：覆盖无进制字母的 SV 填充字面量 `` `W'0 `` / `` `W'1 ``；
- 未声明 → 不扩展；声明非法（非串 / 不能编译 / 匹配空串）→ fail-fast。
"""
import re

import pytest

from core.define import DEFAULT_RULES_DIR
from core.errors import ConfigError
from preprocessor._expand import _extend_macro_chain, _extend_literal_suffix
from preprocessor.macro_shape import load_macro_call_suffix

pytestmark = pytest.mark.smoke

_RULES = DEFAULT_RULES_DIR


def _suffix(recognition: dict) -> re.Pattern | None:
    return load_macro_call_suffix(cfg={"macro_recognition": recognition})


# ── 声明面 ──────────────────────────────────────────────────────────


def test_language_pack_declares_suffix_pattern(config_loaded) -> None:
    """verilog 声明了后缀模式，匹配 IEEE 位宽字面量与 SV 填充字面量。"""
    del config_loaded
    pattern = load_macro_call_suffix(rules_dir=_RULES)
    assert pattern is not None
    for text in ("'d0", "'h1F", "'sb101", "'Sd12", "'b0", "'o7", "'x", "'0", "'1"):
        m = pattern.match(text)
        assert m is not None and m.group(0) == text, text


def test_no_declaration_returns_none(config_loaded) -> None:
    """未声明后缀模式 → None（该语言不做后缀扩展，不是错误）。"""
    del config_loaded
    assert load_macro_call_suffix(rules_dir="grammar/c4") is None
    assert _suffix({"shape": "symbol.base.backtick,name"}) is None


@pytest.mark.parametrize(
    "pattern, match",
    [
        (123, "非空形态模式字符串"),
        ("", "非空形态模式字符串"),
        ("'[sS", "不是合法正则"),
        ("'?", "须至少匹配一个字符"),
    ],
)
def test_illegal_pattern_fails_fast(pattern: object, match: str) -> None:
    """声明非法 → ConfigError（不静默降级成“不扩展”）。"""
    with pytest.raises(ConfigError, match=match):
        _suffix({"suffix_after_call": pattern})


# ── 生效面：区间扩展与 token 边界对齐 ───────────────────────────────


def test_suffix_extends_call_range(config_loaded) -> None:
    """有声明：`` `W'd0 `` 整体纳入调用区间（后缀随宏调用一起替换）。"""
    del config_loaded
    pattern = load_macro_call_suffix(rules_dir=_RULES)
    line = "  assign a = `W'd0;"
    end = line.index("`W") + 2
    assert _extend_literal_suffix(line, end, pattern) == end + len("'d0")


def test_no_pattern_keeps_call_range(config_loaded) -> None:
    """无声明：不动区间（不猜语言字符）。"""
    del config_loaded
    line = "  assign a = `W'd0;"
    end = line.index("`W") + 2
    assert _extend_literal_suffix(line, end, None) == end


def test_chain_merges_literal_and_adjacent_call(config_loaded) -> None:
    """链扩展：后缀 + 后随相邻宏调用合并为单个调用区间（`` `W'd`RST ``）。"""
    del config_loaded
    pattern = load_macro_call_suffix(rules_dir=_RULES)
    macro_re = re.compile(r"`(\w+)")
    line = "  x = `W'd`RST;"
    start = line.index("`W")
    end = _extend_macro_chain(line, start + 2, macro_re, pattern)
    assert line[start:end] == "`W'd`RST"
