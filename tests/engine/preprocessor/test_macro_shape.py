"""宏形态声明（语言包 `[macro_recognition]` 生产式）：解析 / fail-fast / 词法落地。

形态用**生产式**书写（与 grammar rules 同一套规则：`,` 顺序 / `|` 选择 / token 名），
引擎只做通用解析（见 `preprocessor/macro_shape.py`）：

    directive = "symbol.base.backtick,(macro.define|macro.undef|...)"
    call      = "symbol.base.backtick,id"

- 前缀位 = token 名 → 符号文本取自 token 定义（引擎不硬编码语言字符）；
- 名字位 = `id`（任意标识符）或 `macro.<关键字>` 候选（命中即产出该 token 类型）。

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


# ── 声明面（生产式解析） ─────────────────────────────────────────────


def test_language_pack_declares_production_shapes(config_loaded) -> None:
    """verilog：指令段 = 前缀 token + 指令候选集；调用段 = 前缀 token + id。"""
    del config_loaded  # fixture 依赖（语言包配置加载）
    shapes = load_macro_shapes(rules_dir=DEFAULT_RULES_DIR)
    assert set(shapes) == {KIND_DIRECTIVE, KIND_CALL}
    assert shapes[KIND_DIRECTIVE].prefix == "`"
    assert shapes[KIND_CALL].prefix == "`"
    assert shapes[KIND_CALL].names == (), "名字位写 id → 任意标识符（候选集为空）"
    assert len(shapes[KIND_DIRECTIVE].names) == 20
    assert "define" in macro_keywords(shapes[KIND_DIRECTIVE])
    assert "default_nettype" in macro_keywords(shapes[KIND_DIRECTIVE])


def test_prefix_text_read_from_token_definition(config_loaded) -> None:
    """前缀文本按 token 名从 token 定义取（换表 → 前缀跟着变，引擎不写死）。"""
    del config_loaded
    shapes = load_macro_shapes(
        cfg={"macro_recognition": {"directive": "symbol.base.dollar,(macro.define)"}},
        token_define={"symbol": {"base": {"dollar": "$"}}},
    )
    assert shapes[KIND_DIRECTIVE].prefix == "$"
    assert macro_keywords(shapes[KIND_DIRECTIVE]) == ("define",)


def test_undeclared_prefix_token_fails_fast(config_loaded) -> None:
    """语言包内前缀 token 名未声明 → fail-fast（名字写错即配置错）。"""
    del config_loaded
    with pytest.raises(ConfigError, match="未在 token 定义中声明"):
        load_macro_shapes(
            cfg={"macro_recognition": {"call": "symbol.base.nope,id"}},
            token_define=_TD,
        )


def test_injected_token_table_skips_unresolvable_shape(config_loaded) -> None:
    """调用方自建 token 表（测试/嵌入方）：表里没有的前缀 token → 该形态不适用。"""
    del config_loaded
    shapes = load_macro_shapes(
        cfg={"macro_recognition": {"call": "symbol.base.backtick,id"}},
        token_define={"symbol": {"base": {}}},
        skip_undeclared_prefix=True,
    )
    assert shapes == {}


def test_language_without_shape_declaration(config_loaded) -> None:
    """未声明 `[macro_recognition]` 的语言包 → 无形态、空前缀（语言切换不串味）。"""
    del config_loaded
    assert load_macro_shapes(rules_dir="grammar/c4") == {}
    prefix, directives = _load_config("grammar/c4")
    assert prefix == ""
    assert directives, "已注册的指令处理器名仍算指令名（与声明无关的兜底面）"


@pytest.mark.parametrize(
    "production",
    [
        "symbol.base.backtick,id,id",                 # 三位（未实现形态）
        "symbol.base.backtick,literal.number",        # 名字位非 id / macro.*
        "symbol.base.backtick,(id|macro.define)",     # 候选中混入 id
        "literal.number,id",                          # 前缀位不是 symbol token
        "@Foo,id",                                    # 前缀位不是 token
        "symbol.base.backtick",                       # 只有一位
    ],
)
def test_illegal_shape_fails_fast(config_loaded, production: str) -> None:
    """未实现/非法形态 → ConfigError（不静默降级）。"""
    del config_loaded
    with pytest.raises(ConfigError):
        load_macro_shapes(
            cfg={"macro_recognition": {"directive": production}}, token_define=_TD
        )


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
    """名字不在候选内 → macro.call（引擎协议常量）。"""
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
