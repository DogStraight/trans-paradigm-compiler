"""tests/languages/c/test_c_lexer.py — C 包词法面（阶段 2b 收官）。

覆盖：数字形态（整数三种进制 + 后缀 + **前导点浮点** `.5`）、字符与字符串转义
（含 `[string] escape` 的段内转义）、注释。

⚠ 本文件曾有 `TestRecordedLexicalGaps`（把"已知词法缺口"钉成用例，修好后失败以提醒
同步缺口档）——**三条缺口（整型后缀 / 转义引号 / 前导点浮点）已全部修好并按纪律转为
正向断言**，该类随之删除（不留空壳；历史在 git log 与缺口档）。

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
            "5.",         # 点后无小数位（C99 `digit-sequence .` 分支）
            "1e10",       # 指数
            "1.e5",       # 小数位为空的指数形态
            # ── 前导点浮点（C99 §6.4.4.3 `digit-sequence? . digit-sequence`）──
            ".5", ".25",  # 点后必须有数字（`.` 本身仍归符号表，见下）
            ".5e3", ".5E-3", ".5f",
            # ── 后缀（C99 §6.4.4.1，`[[number.based]] suffix 键）──
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

    def test_leading_dot_needs_digits_after(self, c_lexer):
        """`.` 与 `.b` 仍是**符号**（成员访问）——前导点形态要求点后至少一位数字。"""
        assert _types(".", c_lexer) == ["symbol.base.dot"]
        assert _types("a.b", c_lexer) == ["id", "symbol.base.dot", "id"]
        assert _types("p.b.c", c_lexer) == [
            "id",
            "symbol.base.dot",
            "id",
            "symbol.base.dot",
            "id",
        ]

    def test_leading_dot_in_context(self, c_lexer):
        assert _types("x = .5 + .25;", c_lexer) == [
            "id",
            "symbol.base.equal",
            "literal.number",
            "symbol.base.add",
            "literal.number",
            "symbol.base.semicolon",
        ]

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

    @pytest.mark.parametrize(
        "src",
        [
            r'"a\"b"',              # 转义引号（曾在此提前收尾 → 切成多个 token）
            r'"say \"hi\""',        # 真实代码里最常见的一处
            r"'\''",                # 字符常量里的转义单引号
            r'"C:\\path"',          # 转义反斜杠
            r'"a\\"',               # 以转义反斜杠结尾（转义符在结尾的边界）
        ],
    )
    def test_escaped_delimiter_stays_one_token(self, c_lexer, src):
        """段内转义（`[string] escape`）：`\\` 后的字符整体并入、不参与终止判定。

        旧缺陷：delim 捕获按"下一个定界符"结束，不识别反斜杠转义 → `"a\\"b"` 在
        `\\"` 处收尾，后续文本被当成新 token（`printf("say \\"hi\\"")` 这类真实
        代码直接崩）。修法 = 段级声明转义字符（引擎零语言知识，见
        `lexer/capture_runner.py`）。
        """
        types = _types(src, c_lexer)
        assert types == ["literal.string"], f"{src!r} 未按单个字符串捕获：{types}"

    def test_escaped_newline_is_line_splicing(self, c_lexer):
        """`\\` + 换行 = 行拼接（C99 §5.1.1.2）：并入**同一个** token。"""
        toks = [t for t in c_lexer.tokenize('"a\\\nb"\n') if t.type not in ("space",)]
        assert [t.type for t in toks if t.type != "newline"] == ["literal.string"]

    def test_unescaped_quote_still_terminates(self, c_lexer):
        """对照：没有反斜杠的裸引号照旧收尾（`"a" "b"` 是两个字符串）。"""
        assert _types('"a" "b"', c_lexer) == ["literal.string", "literal.string"]


class TestComments:
    def test_line_comment(self, c_lexer):
        assert _types("// c\nx", c_lexer) == ["id"]

    def test_block_comment(self, c_lexer):
        assert _types("/* c */ x", c_lexer) == ["id"]
