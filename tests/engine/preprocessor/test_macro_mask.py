"""宏调用**掩码**：字符串/字符/行注释/块注释内的文本不参与匹配（①，与裸匹配同扫描）。

三层判据：
1. 引擎级 `expand_text`：掩码区间内的宏名不展开；
2. **调用点级**（真实 C 声明）：C 的裸标识符调用生效，但字符串/注释内的同名标识符不展开；
3. 回归：无宏表（未 `#define`）时 `expand_tokens` **逐字节恒等**（普通标识符不被当宏）。
"""
import pytest

from lexer.comment_syntax import load_comment_syntax
from preprocessor.macro_expand import expand_text, mask_spans
from preprocessor.macro_shape import MacroCallArgs, MacroOperators
from preprocessor._expand import expand_tokens

pytestmark = pytest.mark.smoke

_CALL_ARGS = MacroCallArgs(
    open="(", close=")", separator=",", nesting=(("(", ")"),)
)
#: C 的算子与字符串形态（与语言包声明同值；引擎级测试手工构造）
_OPS = MacroOperators(
    stringize="#",
    paste="##",
    variadic="__VA_ARGS__",
    string_delimiters=('"', "'"),
    escape="\\",
)


def _c_syntax():
    return load_comment_syntax("grammar/c")


def test_mask_spans_covers_strings_and_comments() -> None:
    """掩码区间覆盖：字符串、字符、行注释、块注释。"""
    text = 'a = "FOO"; b = \'F\'; c = 1; // FOO\n/* FOO */ d = 2;'
    spans = mask_spans(text, _OPS.string_delimiters, _OPS.escape, _c_syntax())
    masked = "".join(text[a:b] for a, b in spans)
    assert '"FOO"' in masked
    assert "'F'" in masked
    assert "// FOO" in masked
    assert "/* FOO */" in masked
    assert "a = " not in masked, "普通代码不得被掩码"


def test_expand_text_does_not_expand_inside_masks() -> None:
    """引擎级：字符串/块注释内的宏名不展开，代码里的展开。"""
    text = 'x = FOO; s = "FOO"; /* FOO */ y = FOO;'
    out = expand_text(
        text,
        {"FOO": "1"},
        {},
        _CALL_ARGS,
        prefix="",
        operators=_OPS,
        syntax=_c_syntax(),
    )
    assert out == 'x = 1; s = "FOO"; /* FOO */ y = 1;'


def test_call_site_bare_expands_but_strings_and_comments_do_not() -> None:
    """**调用点级**（真实 C 声明）：裸调用展开；字符串/行注释/块注释内不展开。"""
    src = (
        "#define FOO 1\n"
        'int a = FOO;\n'
        'const char *s = "FOO";\n'
        "// FOO\n"
        "/* FOO */ int b = FOO;\n"
    )
    out = expand_tokens(src, {"FOO": "1"}, rules_dir="grammar/c")[0]
    lines = out.splitlines()
    assert lines[1] == "int a = 1;"
    assert lines[2] == 'const char *s = "FOO";'
    assert lines[3] == "// FOO"
    assert lines[4] == "/* FOO */ int b = 1;"


def test_empty_macro_table_is_identity() -> None:
    """无宏表 ⇒ 展开恒等（普通标识符永不因"形态像宏"被展开）。"""
    src = "int main(void) {\n    return FOO + bar;\n}\n"
    assert expand_tokens(src, {}, rules_dir="grammar/c")[0] == src
