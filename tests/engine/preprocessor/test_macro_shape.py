"""宏形态声明（语言包 `[macro_recognition]`）：生产式形状 + 候选列表枚举。

```
[macro_recognition]
shape     = "symbol.base.backtick,name"        # 前缀 token 名 + 名字位占位符
directive = ["macro.define", "macro.undef", ...]   # 名字位候选（列表枚举）
call      = []                                     # 空列表 = 任意标识符
```

- 前缀位写 token 名 → 符号文本取自 token 定义（引擎不硬编码语言字符）；
- 名字位候选命中哪个就产出哪个 token 类型；空列表 = 任意标识符（→ macro.call）；
- 整段不声明 = 该形态不识别。

`` ` `` 同时是 `symbol.base.backtick` 与宏前缀：“前缀 + 名字”成立按宏识别，
裸 `` ` `` 落符号分支。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from core.errors import ConfigError
from lexer import Lexer
from preprocessor._expand import _load_config
from preprocessor.macro_shape import (
    KIND_CALL,
    KIND_DIRECTIVE,
    load_macro_shapes,
    macro_keywords,
)

pytestmark = pytest.mark.smoke

_TD = {"symbol": {"base": {"backtick": "`"}}}


def _lex(src: str) -> list[tuple[str, str]]:
    return [(t.type, t.content) for t in Lexer(rules_dir=DEFAULT_RULES_DIR).tokenize(src)]


def _shapes(recognition: dict, td: dict | None = None) -> dict:
    return load_macro_shapes(
        cfg={"macro_recognition": recognition}, token_define=td or _TD
    )


# ── 声明面（形状解析 + 候选列表） ────────────────────────────────────


def test_language_pack_declares_shape_and_candidates(config_loaded) -> None:
    """verilog：形状 = 前缀 token + 名字位；指令候选列表 20 项；call 空 = 任意名。"""
    del config_loaded  # fixture 依赖（语言包配置加载）
    shapes = load_macro_shapes(rules_dir=DEFAULT_RULES_DIR)
    assert set(shapes) == {KIND_DIRECTIVE, KIND_CALL}
    assert shapes[KIND_DIRECTIVE].prefix == "`"
    assert shapes[KIND_CALL].prefix == "`"
    assert shapes[KIND_CALL].names == (), "空候选列表 → 名字位任意标识符"
    assert len(shapes[KIND_DIRECTIVE].names) == 20
    assert "define" in macro_keywords(shapes[KIND_DIRECTIVE])
    assert "default_nettype" in macro_keywords(shapes[KIND_DIRECTIVE])


def test_prefix_text_read_from_token_definition(config_loaded) -> None:
    """前缀文本按 token 名从 token 定义取（换表 → 前缀跟着变，引擎不写死）。"""
    del config_loaded
    shapes = _shapes(
        {"shape": "symbol.base.dollar,name", "directive": ["macro.define"]},
        td={"symbol": {"base": {"dollar": "$"}}},
    )
    assert shapes[KIND_DIRECTIVE].prefix == "$"
    assert macro_keywords(shapes[KIND_DIRECTIVE]) == ("define",)


def test_undeclared_prefix_token_fails_fast(config_loaded) -> None:
    """语言包内前缀 token 名未声明 → fail-fast（名字写错即配置错）。"""
    del config_loaded
    with pytest.raises(ConfigError, match="未在 token 定义中声明"):
        _shapes({"shape": "symbol.base.nope,name", "call": []})


def test_injected_token_table_skips_unresolvable_shape(config_loaded) -> None:
    """调用方自建 token 表（测试/嵌入方）：表里没有的前缀 token → 该形态不适用。"""
    del config_loaded
    shapes = load_macro_shapes(
        cfg={"macro_recognition": {"shape": "symbol.base.backtick,name", "call": []}},
        token_define={"symbol": {"base": {}}},
        skip_undeclared_prefix=True,
    )
    assert shapes == {}


def test_segment_without_shape_fails_fast(config_loaded) -> None:
    """声明了形态段却没有 shape → fail-fast（形状缺失不静默忽略）。"""
    del config_loaded
    with pytest.raises(ConfigError, match="缺 shape"):
        _shapes({"directive": ["macro.define"]})


def test_language_without_shape_declaration(config_loaded) -> None:
    """未声明 `[macro_recognition]` 的语言包 → 无形态、空前缀（语言切换不串味）。"""
    del config_loaded
    assert load_macro_shapes(rules_dir="grammar/c4") == {}
    prefix, directives = _load_config("grammar/c4")
    assert prefix == ""
    assert directives, "已注册的指令处理器名仍算指令名（与声明无关的兜底面）"


@pytest.mark.parametrize(
    "shape",
    [
        "symbol.base.backtick,id",        # 名字位不是 name 占位符
        "name,symbol.base.backtick",      # 后缀序未实现
        "symbol.base.backtick,name,name",  # 三位
        "literal.number,name",            # 前缀位不是 symbol token
        "@Foo,name",                      # 前缀位不是 token
        "symbol.base.backtick",           # 只有一位
    ],
)
def test_illegal_shape_fails_fast(config_loaded, shape: str) -> None:
    """未实现/非法形状 → ConfigError（不静默降级）。"""
    del config_loaded
    with pytest.raises(ConfigError):
        _shapes({"shape": shape, "directive": ["macro.define"]})


@pytest.mark.parametrize(
    "value",
    [
        "macro.define",            # 字符串而非列表
        ["define"],                # 候选缺 macro. 协议前缀
        [123],                     # 候选不是字符串
        {"define": True},          # 表而非列表
    ],
)
def test_illegal_candidates_fail_fast(config_loaded, value: object) -> None:
    """候选列表非法 → ConfigError。"""
    del config_loaded
    with pytest.raises(ConfigError):
        _shapes({"shape": "symbol.base.backtick,name", "directive": value})


# ── 词法落地（声明 → token 类型） ────────────────────────────────────


def test_directive_names_come_from_declaration(config_loaded) -> None:
    """命中指令候选 → 产出该候选名作为 token 类型（声明即真相）。"""
    del config_loaded
    assert _lex("`timescale 1ns/1ps\n")[0] == ("macro.timescale", "`timescale")
    assert _lex("`define A 1\n")[0] == ("macro.define", "`define")
    assert _lex("`default_nettype wire\n")[0] == (
        "macro.default_nettype",
        "`default_nettype",
    )


def test_unknown_name_is_macro_call(config_loaded) -> None:
    """名字不在候选内 → macro.call（call 段空列表接管任意标识符）。"""
    del config_loaded
    assert _lex("`NOT_A_DIRECTIVE\n")[0] == ("macro.call", "`NOT_A_DIRECTIVE")


def test_bare_prefix_falls_back_to_symbol(config_loaded) -> None:
    """裸 `` ` ``（无名字）不是宏形态 → 落符号分支 symbol.base.backtick。"""
    del config_loaded
    types = _lex("wire a = `;\n")
    assert ("symbol.base.backtick", "`") in types
    assert all(t != "macro.call" for t, _ in types)


def test_prefix_not_swallowing_other_tokens(config_loaded) -> None:
    """宏形态识别不影响相邻词法：无尺寸字面量 / 前缀后接非标识符。"""
    del config_loaded
    assert ("literal.number", "'d0") in _lex("x = 'd0;\n")
    assert ("literal.number", "1") in _lex("wire a = `1;\n")
