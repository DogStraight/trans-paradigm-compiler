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
            # ── C23 §6.4.4.1 二进制常量（0b/0B；c23 档声明，基线档仍切两个 token）──
            "0b1010", "0B101", "0b1010u", "0b1010ULL",
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


class TestLiteralPrefixes:
    """字面量**前缀**（引擎声明面 `[string] prefixes`；C 包按档位声明 L / u / U / u8）。

    前缀是 token 的一部分（与定界符紧邻），内容含前缀、渲染原样输出——旧实现切
    `id` + `literal.string` 两 token，导致 `u8"x"` / `L'x'` 这类合法 C 代码解析失败。
    """

    @pytest.mark.parametrize(
        "src",
        [
            'L"wide"', "L'w'",     # C99 宽字符/宽字符串
            'u"utf16"', "u'w'",    # C11 Unicode 字符串/字符
            'U"utf32"', "U'w'",    # C11 Unicode 字符串/字符
            'u8"utf8"',            # C11 UTF-8 字符串
            "u8'w'",               # C23 UTF-8 字符常量（默认档 = c23 全档）
        ],
    )
    def test_prefixed_literal_is_single_token(self, c_lexer, src):
        assert _types(src, c_lexer) == ["literal.string"], f"{src!r} 不是一个 token"

    @pytest.mark.parametrize(
        "src",
        ['L"x"', "L'x'", 'u8"x"', "u8'x'"],
    )
    def test_prefix_kept_in_token_content(self, c_lexer, src):
        """前缀进 token **正文**（`u8"x"` 不再是 `u8` + `"x"`）。"""
        toks = [t for t in c_lexer.tokenize(src + "\n") if t.type == "literal.string"]
        assert [t.content for t in toks] == [src]

    def test_prefix_must_be_adjacent(self, c_lexer):
        """前缀与定界符之间**不是**空白（`u8 "x"` 是两个 token，不是字面量）。"""
        assert _types('u8 "x"', c_lexer) == ["id", "literal.string"]
        assert _types("L 'x'", c_lexer) == ["id", "literal.string"]


class TestLiteralPrefixTiers:
    """前缀的**档位面**：L（C99 基线）→ u/U/u8 字符串（C11）→ u8 字符（C23）。

    判据 = "同一个字面量在未达档位时被切成两个 token"（接受域 = 声明面组合），
    与 `tests/languages/c/test_c_standard_conformance.py` 的端到端判据互补。
    """

    _CASES = [
        # (档位, 源码, 期望 token 类型序列)
        ("baseline", 'L"x"', ["literal.string"]),
        ("baseline", "L'x'", ["literal.string"]),
        ("baseline", 'u"x"', ["id", "literal.string"]),
        ("baseline", 'u8"x"', ["id", "literal.string"]),
        ("baseline", "0b1010", ["literal.number", "id"]),
        ("c11", 'u"x"', ["literal.string"]),
        ("c11", "U'x'", ["literal.string"]),
        ("c11", 'u8"x"', ["literal.string"]),
        ("c11", "u8'x'", ["id", "literal.string"]),      # u8 字符是 C23
        ("c11", "0b1010", ["literal.number", "id"]),      # 二进制是 C23
        ("c23", "u8'x'", ["literal.string"]),
        ("c23", "0b1010", ["literal.number"]),
    ]
    _TIERS = {
        "baseline": [],
        "c11": ["c11"],
        "c23": ["c11", "c17", "c23"],
    }

    @pytest.mark.parametrize(
        "tier,src,expected", _CASES, ids=[f"{c[0]}-{c[1]}" for c in _CASES]
    )
    def test_token_split_follows_tier(self, tier, src, expected):
        ConfigRegistry.load_language(
            _RULES, plugins_dir=os.path.join(_RULES, "plugins"), enabled=self._TIERS[tier]
        )
        lexer = Lexer(rules_dir=_RULES)
        got = [
            t.type
            for t in lexer.tokenize(src + "\n")
            if t.type not in ("newline", "comment")
        ]
        assert got == expected, f"{tier} 档下 {src!r} 切分不符：{got}"

    @pytest.fixture(autouse=True)
    def _restore(self):
        yield
        ConfigRegistry.load_language(
            _RULES, plugins_dir=os.path.join(_RULES, "plugins")
        )
