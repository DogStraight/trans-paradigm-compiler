"""tests/languages/c/test_c_lexer.py — C 包词法面（阶段 2b 收官）。

覆盖：数字形态（整数三种进制 + 浮点小数/指数）、字符与字符串转义、注释。
并把**两条残留缺口钉成用例**（整型后缀、前导点浮点）——缺口修好后对应用例会失败
并提醒同步缺口档，而不是让"残缺"静默通过。

⚠ 转义样本一律用 **raw string**（`r"'\n'"`）表达"源码里就是反斜杠 n"，
不要用会先被 Python 解释一层再被断言解释一层的写法（本轮为此踩过一次）。
"""

import os

import pytest

from core.config_registry import ConfigRegistry
from lexer import Lexer

_RULES = "grammar/c"


@pytest.fixture(scope="module")
def c_lexer(config_loaded):
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=os.path.join(_RULES, "plugins"))
    yield Lexer(rules_dir=_RULES)
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _types(src: str, c_lexer) -> list[str]:
    """token 类型序列（滤掉 newline 与 comment——它们不参与"字面量形态"断言）。"""
    return [
        t.type
        for t in c_lexer.tokenize(src + "\n")
        if t.type not in ("newline", "comment")
    ]


class TestNumberForms:
    @pytest.mark.parametrize(
        "src",
        [
            "0",          # 零
            "017",        # 前导 0 八进制
            "0x1F",       # 十六进制
            "0X1f",       # 十六进制大写前缀
            "123",        # 十进制
            "3.14",       # 小数
            "0.5",        # **0 开头的小数**（判据样本：digits=nonzero 时会被拆成 0 + .5）
            "1e10",       # 指数
            "1.e5",       # 小数位为空的指数形态
            # ── 后缀（C99 §6.4.4.1，`[[number.based]] suffix 键，2026-09-25 接上）──
            "42u", "42U",             # unsigned-suffix
            "10L", "10l",             # long-suffix
            "1LL", "1ll", "1ULL", "1LLU",   # long-long（含与 unsigned 的组合，3 字符）
            "0xFFu", "0X1fUL", "017UL",     # 十六进制/八进制 + 后缀
            "1.5f", "1.5F", "1.5L",   # floating-suffix
            "1e3L", "2.3e-4f",        # 指数 + 后缀
        ],
    )
    def test_single_number_token(self, c_lexer, src):
        assert _types(src, c_lexer) == ["literal.number"], f"{src!r} 不是单个数字 token"

    def test_suffix_kept_in_token_content(self, c_lexer):
        """后缀进 token **正文**（不只类型对）——`42u` 不再是 `42` + `u`。"""
        toks = [t for t in c_lexer.tokenize("1ULL\n") if t.type == "literal.number"]
        assert [t.content for t in toks] == ["1ULL"]

    def test_number_then_identifier_still_splits(self, c_lexer):
        """对照：真正的"数字后跟标识符"仍切两 token（后缀是闭集，不许吞标识符）。"""
        assert _types("456abc", c_lexer) == ["literal.number", "id"]

    def test_suffix_stops_at_declared_max(self, c_lexer):
        """`max` 封顶：`1u2` → `1u` + `2`（超额字符留给下一个 token）。"""
        assert _types("1u2", c_lexer) == ["literal.number", "literal.number"]

    def test_numbers_in_expression_context(self, c_lexer):
        assert _types("x = 0.5 + 1e3;", c_lexer) == [
            "id",
            "symbol.base.equal",
            "literal.number",
            "symbol.base.add",
            "literal.number",
            "symbol.base.semicolon",
        ]


class TestEscapes:
    @pytest.mark.parametrize(
        "src",
        [r"'\n'", r"'\t'", r"'\\'", r"'\0'", "'a'"],
    )
    def test_char_literal_escapes(self, c_lexer, src):
        assert _types(src, c_lexer) == ["literal.string"], f"{src!r} 未按字符常量捕获"

    @pytest.mark.parametrize(
        "src",
        [r'"a\tb"', r'"\x41"', '""'],
    )
    def test_string_literal_escapes(self, c_lexer, src):
        assert _types(src, c_lexer) == ["literal.string"], f"{src!r} 未按字符串捕获"


class TestComments:
    def test_line_comment(self, c_lexer):
        assert _types("// c\nx", c_lexer) == ["id"]

    def test_block_comment(self, c_lexer):
        assert _types("/* c */ x", c_lexer) == ["id"]


class TestRecordedLexicalGaps:
    """⚠ **已知词法缺口**（钉成用例：修好后会失败 → 提醒同步缺口档与 TODO）。

    1. **前导点浮点**（`.5`）：数字形态由 `size` / `base_prefix` 描述，表达不了
       "以点开头"的浮点，故被切成"点 + 数字"。
    2. **转义引号**（`"a\\"b"`）：delim 捕获不识别反斜杠转义。

    ⚠ **整型后缀**（`42u` / `0xFFu` / `10L` / `1ULL`）已于 2026-09-25 修好
    （`[[number.based]]` 新增 `suffix` 键）——按本类的用法（"修好后用例会失败并提醒
    同步"），对应用例已**转为正向断言**（见 `TestNumberForms`）。
    """

    def test_escaped_quote_inside_string_breaks_capture(self, c_lexer):
        """**转义引号**（`"a\\"b"`）让字符串捕获提前终止。

        delim 模式的捕获按"下一个定界符"结束，**不识别反斜杠转义**（见
        `docs/gaps/gap-lexer-capture-boundaries.md` 的同类记录）。真实代码里
        `printf("say \\"hi\\"")` 很常见，故这是**有实际影响**的缺口。
        本用例钉住现状：修好后会失败并提醒同步缺口档。
        """
        types = _types(r'"a\"b"', c_lexer)
        assert "literal.string" in types and len(types) > 1, (
            f"转义引号的 token 形态变了（现为 {types}）——若已支持，"
            "请改断言并同步缺口档"
        )

    def test_leading_dot_float_still_splits(self, c_lexer):
        assert _types(".5", c_lexer) == ["symbol.base.dot", "literal.number"], (
            "`.5` 的 token 形态变了——若已支持，请改断言并同步缺口档"
        )
