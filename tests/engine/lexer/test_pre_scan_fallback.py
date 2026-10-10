"""预扫描 `fallback` 开关（`[pre_scan] fallback = bool`）判据。

动机（2026-10-10，C 语义基座 P1 实测）：引擎原先**无条件**为所有声明关键字建
`\\b(kw)\\s+(\\w+)` 兜底正则 ⇒ C 包按 `phase` 做符号对比时会拿到 `int: typedef`、
`struct: typedef` 这类**非声明名**杂质，而包侧无法关闭。新增 `fallback`
（默认 `true` = 原行为）后，需要干净符号面的语言包可显式 `fallback = false`；
**声明类别（`[pre_scan.decl.*]`）的收集不受该键影响**。

Doc: docs/language_walkthrough.md（预扫描：顶层声明收集）
"""

import pytest

from core.errors import ConfigError
from lexer.pre_scan import _compile, load_pre_scan_config, pre_scan

_SRC = "typedef int myint;\nstruct point p;\n"


def _cfg(fallback=None):
    cfg = {
        "context_keywords": [],
        "decl": {
            "typedef": {
                "keyword": "typedef",
                "name_capture": "last_word_before_semicolon",
            }
        },
        "clean": [],
    }
    if fallback is not None:
        cfg["fallback"] = fallback
    return cfg


class TestFallbackSwitch:
    """默认 true（原行为）/ false（干净面）/ 非 bool 即 fail-fast。"""

    def test_default_keeps_fallback_behavior(self):
        """不声明 `fallback` ⇒ 保持引擎原行为（兜底把"关键字后那个词"也收成该类别）。"""
        sym = pre_scan(_SRC, _compile(_cfg()))
        assert sym.get("myint") == "typedef"  # 声明类别（分号前末词）
        assert sym.get("int") == "typedef"  # 兜底杂质：`typedef int` 的下一词

    def test_false_drops_fallback_but_keeps_declared_kinds(self):
        """`fallback = false` ⇒ 只留声明类别；兜底带来的词不进结果。"""
        sym = pre_scan(_SRC, _compile(_cfg(fallback=False)))
        assert sym.get("myint") == "typedef"
        assert "point" not in sym
        assert "int" not in sym

    def test_non_bool_is_fail_fast(self):
        """类型错即报错（配置 fail-fast），不静默降级。"""
        with pytest.raises(ConfigError):
            _compile(_cfg(fallback="false"))


class TestCPackPreScanFace:
    """C 包已声明 `fallback = false`：符号面不含关键字杂质，声明类别仍在。"""

    def test_c_pack_symbols_are_clean(self):
        cfg = load_pre_scan_config("grammar/c")
        sym = pre_scan(
            "typedef int myint;\nstruct point { int x; };\nint plain;\n",
            cfg,
        )
        assert sym.get("myint") == "typedef"
        assert sym.get("point") == "tag_struct"
        # 兜底杂质不得出现（`int`/`struct` 这类关键字本身、以及 `int x` 里的 `x`）
        assert "int" not in sym
        assert "struct" not in sym
        assert "x" not in sym
        assert "plain" not in sym
