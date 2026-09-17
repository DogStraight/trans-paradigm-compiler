"""带参宏实参形态（语言包 `[macro_recognition]` 的 `call_args` / `arg_separator`）。

```
[macro_recognition]
call_args     = "bracket.l_parentheses,args,bracket.r_parentheses"
arg_separator = "symbol.base.comma"
```

- 括号对文本取自 `[bracket].pairs`、分隔符文本取自 `[symbol.*]`（引擎不硬编码
  `(` / `,`）；配平计深的括号对 = 语言包声明的**全部**括号对；
- 定义侧（`` `define NAME(a, b) ``）与调用侧（`` `NAME(x, y) ``）同形共用；
- 声明非法 / 有待参宏却没声明 → fail-fast（不静默降级）。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from core.errors import ConfigError
from preprocessor._expand import expand_tokens, scan_directives
from preprocessor.macro_shape import MacroCallArgs, load_macro_call_args

pytestmark = pytest.mark.smoke

_RULES = DEFAULT_RULES_DIR
# 自建 token 表：多字符括号对 + 自定义分隔符（证明引擎不假设单字符 `(` / `,`）
_TD = {
    "bracket": {"pairs": [["<<", ">>", "angle"], ["(", ")", "parentheses"]]},
    "symbol": {"base": {"comma": ",", "semicolon": ";"}},
}


def _call_args(recognition: dict, td: dict | None = None) -> MacroCallArgs | None:
    return load_macro_call_args(
        cfg={"macro_recognition": recognition}, token_define=td or _TD
    )


# ── 声明面 ──────────────────────────────────────────────────────────


def test_language_pack_declares_call_args(config_loaded) -> None:
    """verilog：括号对 / 分隔符文本与配平括号对都来自声明。"""
    del config_loaded
    call_args = load_macro_call_args(rules_dir=_RULES)
    assert call_args is not None
    assert (call_args.open, call_args.close, call_args.separator) == ("(", ")", ",")
    assert ("(", ")") in call_args.nesting
    assert ("[", "]") in call_args.nesting, "嵌套括号对取自 [bracket].pairs 全量"
    assert ("{", "}") in call_args.nesting


def test_texts_read_from_token_definition() -> None:
    """括号/分隔符文本按 token 名从 token 定义取（换表 → 文本跟着变）。"""
    call_args = _call_args(
        {
            "call_args": "bracket.l_angle,args,bracket.r_angle",
            "arg_separator": "symbol.base.semicolon",
        }
    )
    assert call_args is not None
    assert (call_args.open, call_args.close, call_args.separator) == ("<<", ">>", ";")


def test_no_declaration_returns_none() -> None:
    """未声明实参形态 → None（该语言不做带参展开，不是错误）。"""
    assert _call_args({"shape": "symbol.base.comma,name"}) is None
    assert load_macro_call_args(rules_dir="grammar/c4") is None


def test_injected_table_without_brackets_skips(config_loaded) -> None:
    """注入的 token 表里没有声明的括号名 → 跳过（调用方的表说了算什么符号存在）。"""
    del config_loaded
    assert (
        load_macro_call_args(
            cfg={
                "macro_recognition": {
                    "call_args": "bracket.l_parentheses,args,bracket.r_parentheses",
                    "arg_separator": "symbol.base.comma",
                }
            },
            token_define={"symbol": {"base": {"comma": ","}}},
            skip_undeclared_prefix=True,
        )
        is None
    )


@pytest.mark.parametrize(
    "recognition, match",
    [
        # 非生产式
        ({"call_args": "(", "arg_separator": "symbol.base.comma"}, "无法解析"),
        # 缺实参槽
        (
            {
                "call_args": "bracket.l_parentheses,bracket.r_parentheses",
                "arg_separator": "symbol.base.comma",
            },
            "须是三位顺序",
        ),
        # 槽名不是 args
        (
            {
                "call_args": "bracket.l_parentheses,name,bracket.r_parentheses",
                "arg_separator": "symbol.base.comma",
            },
            "实参槽占位符",
        ),
        # 括号位不是 bracket token 名
        (
            {
                "call_args": "symbol.base.comma,args,symbol.base.comma",
                "arg_separator": "symbol.base.comma",
            },
            "括号位须是 token 名",
        ),
        # 开闭括号名不一致
        (
            {
                "call_args": "bracket.l_parentheses,args,bracket.r_angle",
                "arg_separator": "symbol.base.comma",
            },
            "名称须一致",
        ),
        # 缺分隔符声明
        ({"call_args": "bracket.l_parentheses,args,bracket.r_parentheses"}, "同时声明"),
        # 分隔符名未声明
        (
            {
                "call_args": "bracket.l_parentheses,args,bracket.r_parentheses",
                "arg_separator": "symbol.base.nope",
            },
            "未在 token 定义中声明",
        ),
        # 空生产式
        ({"call_args": "", "arg_separator": "symbol.base.comma"}, "非空生产式"),
    ],
)
def test_illegal_declaration_fails_fast(recognition: dict, match: str) -> None:
    """声明非法 → ConfigError（名字写错 / 形状不对都不静默忽略）。"""
    with pytest.raises(ConfigError, match=match):
        _call_args(recognition)


# ── 配平（match_args）：嵌套 / 多字符 / 容错 ────────────────────────


def test_match_args_nested_brackets(config_loaded) -> None:
    """配平按声明括号对计深（`[]`、`{}` 内的闭括号不当调用结束）。"""
    del config_loaded
    call_args = load_macro_call_args(rules_dir=_RULES)
    assert call_args is not None
    text = "`M(a[0], {b, c}) + 1"
    matched = call_args.match_args(text, 2)
    assert matched == ("a[0], {b, c}", 16)


def test_match_args_multi_char_brackets() -> None:
    """多字符括号对同样可用（按声明整串匹配，不是按字符）。"""
    call_args = _call_args(
        {
            "call_args": "bracket.l_angle,args,bracket.r_angle",
            "arg_separator": "symbol.base.semicolon",
        }
    )
    assert call_args is not None
    assert call_args.match_args("<<a; <<b>>; c>>", 0) == ("a; <<b>>; c", 15)


def test_match_args_unclosed_returns_none(config_loaded) -> None:
    """未配平（未闭合 / 跨行）→ None，调用方自行容错。"""
    del config_loaded
    call_args = load_macro_call_args(rules_dir=_RULES)
    assert call_args is not None
    assert call_args.match_args("`M(a, b", 2) is None
    assert call_args.match_args("`M(a, b) x", 1) is None, "开括号处才开始配平"
    assert call_args.match_args("`M(a, b) x", 2) is not None


# ── 切分（split）：顶层分隔符 ───────────────────────────────────────


def test_split_top_level_only(config_loaded) -> None:
    """只按顶层分隔符切；括号对内的分隔符保留在实参里。"""
    del config_loaded
    call_args = load_macro_call_args(rules_dir=_RULES)
    assert call_args is not None
    assert call_args.split("a, f(b, c), {d, e}") == ["a", "f(b, c)", "{d, e}"]


def test_split_empty_and_trailing(config_loaded) -> None:
    """空表 / 空实参逐段保留（展开侧按形参顺序绑定，缺则补空串）。"""
    del config_loaded
    call_args = load_macro_call_args(rules_dir=_RULES)
    assert call_args is not None
    assert call_args.split("") == [""]
    assert call_args.split("a, ") == ["a", ""]


def test_split_multi_char_separator() -> None:
    """多字符分隔符同样可用。"""
    call_args = _call_args(
        {
            "call_args": "bracket.l_angle,args,bracket.r_angle",
            "arg_separator": "symbol.base.semicolon",
        }
    )
    assert call_args is not None
    assert call_args.split("a;b") == ["a", "b"]


# ── 落地：定义侧 / 调用侧同源 ───────────────────────────────────────


def _expand(src: str) -> str:
    table, funcs, _c, _h, _d, clean, _m = scan_directives(src, _RULES)
    text, _anchors, _regions, _lm = expand_tokens(
        clean, table, rules_dir=_RULES, func_macros=funcs
    )
    return text


@pytest.mark.usefixtures("config_loaded")
def test_definition_and_call_share_declaration() -> None:
    """形参表与实参表用同一份声明：`define MIN(a, b) → `MIN(1, 2) 形参替换正确。"""
    out = _expand("`define MIN(a, b) ((a) < (b) ? (a) : (b))\nmodule m;\n  x = `MIN(1, 2);\nendmodule\n")
    assert "((1) < (2) ? (1) : (2))" in out


@pytest.mark.usefixtures("config_loaded")
def test_call_args_with_nested_brackets() -> None:
    """调用实参含方括号 / 花括号 / 函数调用：按声明配平，不当成分隔。"""
    out = _expand(
        "`define MIN(a, b) ((a) < (b))\n"
        "module m;\n"
        "  x = `MIN({p, q}, y[0]);\n"
        "endmodule\n"
    )
    assert "({p, q}) < (y[0])" in out


@pytest.mark.usefixtures("config_loaded")
def test_missing_declaration_fails_fast(config_loaded) -> None:
    """有待参宏却没声明实参形态 → ConfigError（不静默降级成“带参也不识别”）。"""
    del config_loaded
    with pytest.raises(ConfigError, match="未声明实参形态"):
        expand_tokens(
            "x = `M(1);\n", {"M": "1'b1"}, rules_dir="grammar/c4", func_macros={"M": ["a"]}
        )
