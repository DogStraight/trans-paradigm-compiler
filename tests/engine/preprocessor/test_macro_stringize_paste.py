"""`#`（字符串化）/ `##`（粘贴）/ `__VA_ARGS__` 语义（对拍 GCC 16.1.0 实测）。

GCC 实测基准（`gcc -E`，task-39 探针）：
- `#define S(a) #a` + `S(hi there)` → `"hi there"`
- `#define CAT(a,b) a##b` + `CAT(EMPTY,x)` → **`EMPTYx`**（`##` 用**未展开拼写**，试金石）
- `#define EMPTY` + `CAT(EMPTY,x)` → `EMPTYx`（不是 `x`）
- `#define F(a, ...) f(a, __VA_ARGS__)` + `F(1)` → **`f(1, )`**（留逗号 = 标准行为）
- `F(1,2,3)` → `f(1, 2,3)`
- `#define G(...) g(__VA_ARGS__)` + `G()` → `g()`；`G(1)` → `g(1)`
"""
import pytest

from preprocessor.macro_expand import expand_text
from preprocessor.macro_shape import MacroCallArgs, MacroOperators

pytestmark = pytest.mark.smoke

_CALL_ARGS = MacroCallArgs(
    open="(", close=")", separator=",", nesting=(("(", ")"),)
)
#: 宏算子由语言包声明（C：`#`/`##`/`__VA_ARGS__`）；未声明 ⇒ 不启用
#: 字符串/字符字面量形态来自 token 表 `[string]`（与 lexer 捕获器同源）
_OPS = MacroOperators(
    stringize="#",
    paste="##",
    variadic="__VA_ARGS__",
    string_delimiters=('"', "'"),
    escape="\\",
)


def _expand(text: str, defs: dict[str, str], funcs: dict[str, list[str]]) -> str:
    return expand_text(text, defs, funcs, _CALL_ARGS, operators=_OPS)


def test_stringize_uses_unexpanded_spelling() -> None:
    """`#` 取未展开拼写：`S(hi there)` → `"hi there"`。"""
    out = _expand(
        "S(hi there)",
        {"S": "#a"},
        {"S": ["a"]},
    )
    assert out == '"hi there"'


def test_stringize_collapses_whitespace_between_tokens() -> None:
    """C99 §6.10.3.2p2：**token 之间**的空白折叠为一个空格（对拍 GCC 16.1.0）。

    反例（`re.sub(r"\\s+")` 一把梭会错）：`S("a  b")` 必须保持字面量内部空白。
    """
    defs = {"S": "#a"}
    funcs = {"S": ["a"]}
    assert _expand("S(a   b)", defs, funcs) == '"a b"', "多空格 → 单空格"
    assert _expand("S(a\tb)", defs, funcs) == '"a b"', "TAB → 单空格"
    assert _expand("S( a )", defs, funcs) == '"a"', "首尾空白丢弃"
    assert _expand('S("a  b")', defs, funcs) == '"\\"a  b\\""', (
        "字符串字面量内部空白不得折叠（GCC oracle）"
    )


def test_variadic_join_uses_declared_separator() -> None:
    """变参连接符来自 `MacroCallArgs.separator`（语言包声明），不是引擎硬编码。"""
    call_args = MacroCallArgs(
        open="(", close=")", separator=";", nesting=(("(", ")"),)
    )
    out = expand_text(
        "G(1;2)",
        {"G": "g(__VA_ARGS__)"},
        {"G": []},
        call_args,
        operators=_OPS,
    )
    assert out == "g(1;2)", "separator=';' ⇒ 变参连接也跟着用 ';'"


def test_paste_uses_unexpanded_spelling_is_the_touchstone() -> None:
    """**试金石**：`CAT(EMPTY,x)` → `EMPTYx`（不是 `x`：`##` 用未展开拼写）。"""
    out = _expand(
        "CAT(EMPTY,x)",
        {"CAT": "a##b", "EMPTY": ""},
        {"CAT": ["a", "b"]},
    )
    assert out == "EMPTYx"


def test_paste_of_identifiers_forms_new_identifier() -> None:
    """`P(fo,o)` → `foo`（粘贴成新标识符；下游重扫描按新 token 判宏表）。"""
    out = _expand("P(fo,o)", {"P": "a##b"}, {"P": ["a", "b"]})
    assert out == "foo"


def test_variadic_keeps_comma_when_empty() -> None:
    """`F(1)`（`f(a, __VA_ARGS__)`）→ `f(1, )`：**留逗号**（标准行为）。"""
    out = _expand("F(1)", {"F": "f(a, __VA_ARGS__)"}, {"F": ["a"]})
    assert out == "f(1, )"


def test_variadic_multiple_args() -> None:
    """`F(1,2,3)` → `f(1, 2,3)`（具名实参 + 变参原样拼接）。"""
    out = _expand("F(1,2,3)", {"F": "f(a, __VA_ARGS__)"}, {"F": ["a"]})
    assert out == "f(1, 2,3)"


def test_variadic_only_macro_empty_call() -> None:
    """`G()`（`g(__VA_ARGS__)`）→ `g()`；`G(1)` → `g(1)`。"""
    defs = {"G": "g(__VA_ARGS__)"}
    funcs = {"G": []}
    assert _expand("G()", defs, funcs) == "g()"
    assert _expand("G(1)", defs, funcs) == "g(1)"
