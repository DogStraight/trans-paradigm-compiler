"""数字**分隔符**（`[[number.based]] digit_separator` 键）测试。

背景：C23 §6.4.4.1 的 digit separator（`1'000'000`）此前表达不了——数字 DFA 里
`'` 没有转移，`1'000` 被切成 `1` + 字符常量（实测 `literal.string "'000'"`）。
修法 = 声明的**单字符分隔符**：编译期在每个"数字自环态"旁挂一个分隔态
（`S --sep--> S'` 非接受、`S' --digit--> S`），故分隔符必须夹在数字之间，而引擎
不知道任何语言——C23/c11 的差别只是**语言包声明**（`grammar/c/plugins/c23/_number_c23.toml`
按名合并给三个核心形态补键；基线/c11 档不声明 ⇒ 仍是两个 token）。

Doc: docs/gaps/gap-language-pack-scope.md（C 标准等效缺口）/ lexer/README.md
"""

import pytest

from core.errors import ConfigError
from lexer.number_gen import compile_number_pattern
from lexer.number_runner import build_number_runner

# C 风格两形态的最小复现（`grammar/c/base/_number.toml` 的 c_prefix / c_dec——
# ⚠ 八进制 digit 序列（`0'7`）由 c_dec 的 `size = { digits = "any" }` 覆盖，故不需要
# 第三条形态：数字扫描取最长 token，`c_octal` 再声明一条分隔符只是重复知识）
C_CFG = [
    {
        "name": "c_prefix",
        "size": "none",
        "base_prefix": "0x|0b",
        "bases": [],
        "value_digits": {"x": "hex", "b": "bin"},
        "value_allow": [],
        "digit_separator": "'",
    },
    {
        "name": "c_dec",
        "size": {"digits": "any"},
        "base_prefix": "none",
        "bases": [],
        "value_digits": {"d": "dec"},
        "value_allow": [],
        "suffix": {"chars": "uUlLfF", "max": 3},
        "digit_separator": "'",
    },
]

# 同一份声明**去掉分隔符键**（= 基线档的切分行为，用作对照）
C_CFG_NO_SEP = [{k: v for k, v in c.items() if k != "digit_separator"} for c in C_CFG]


def _run(src: str, cfgs=C_CFG) -> str:
    runner = build_number_runner(cfgs)
    assert runner is not None
    tok, _ = runner.run(src, 0)
    return tok


class TestDigitSeparatorDeclaration:
    """声明面：读键 / 缺省 / 形态非法 fail-fast。"""

    def test_absent_key_means_no_separator(self):
        pat = compile_number_pattern(
            {"name": "x", "size": {"digits": "any"}, "base_prefix": "none"}
        )
        # 未声明 ⇒ 转移表里没有 quote 类别（`'` 不会成为数字的一部分）
        assert not any(cat == "quote" for _, cat in pat.transitions)

    def test_multi_char_separator_rejected(self):
        with pytest.raises(ConfigError, match="digit_separator"):
            compile_number_pattern(
                {
                    "name": "x",
                    "size": {"digits": "any"},
                    "base_prefix": "none",
                    "digit_separator": "''",
                }
            )

    def test_non_string_separator_rejected(self):
        with pytest.raises(ConfigError, match="digit_separator"):
            compile_number_pattern(
                {
                    "name": "x",
                    "size": {"digits": "any"},
                    "base_prefix": "none",
                    "digit_separator": 39,
                }
            )

    def test_unknown_char_rejected(self):
        """没有字符类别的字符（引擎的全局类别表不认识）→ 配置错误，不静默无效。"""
        with pytest.raises(ConfigError, match="digit_separator"):
            compile_number_pattern(
                {
                    "name": "x",
                    "size": {"digits": "any"},
                    "base_prefix": "none",
                    "digit_separator": "€",
                }
            )

    def test_collision_with_existing_edge_rejected(self):
        """撞键：Verilog `'h…` 的引号前缀态同时有数字自环 ⇒ 不能再当分隔符。"""
        with pytest.raises(ConfigError, match="撞键"):
            compile_number_pattern(
                {
                    "name": "verilog_like",
                    "size": {"digits": "nonzero"},
                    "base_prefix": "'",
                    "bases": ["d"],
                    "value_digits": {"d": "dec"},
                    "digit_separator": "'",
                }
            )


class TestDigitSeparatorScan:
    """扫描面：分隔符夹在数字之间才并入 token，尾随/连续分隔符不并。"""

    @pytest.mark.parametrize(
        "src",
        [
            "1'000'000",     # 十进制（gcc -std=c23 OK）
            "0'7",           # 八进制
            "0x1'F",         # 十六进制（hex digit 大小写）
            "0b1'0",         # 二进制
            "1.5'0",         # 小数位
            "1.0e1'0",       # 指数位
            "1'000u",        # 后缀
        ],
    )
    def test_separated_digits_are_single_token(self, src):
        assert _run(src) == src, f"{src!r} 未整体成 token"

    def test_control_without_declaration_splits(self):
        """干净对照：同一份形态**去掉 digit_separator** ⇒ 在第一个 `'` 处断开。"""
        assert _run("1'000'000", C_CFG_NO_SEP) == "1"

    def test_trailing_separator_not_consumed(self):
        """`1'` 的分隔符不属于 token（否则字符常量永远轮不到）。"""
        assert _run("1'") == "1"

    def test_double_separator_not_consumed(self):
        """连续分隔符在第二个处断开（`1''0` 不是数字 token 前缀）。"""
        assert _run("1''0") == "1"

    def test_separator_between_fraction_digits(self):
        """小数位是独立的数字自环态：`1.5'0` 也能吃到分隔符。"""
        assert _run("1.5'0") == "1.5'0"

    def test_wide_in_positions_not_validated(self):
        """位置合法性**不**在词法层判定（宽进口径同 `1ff`）：`0x'1` / `1.'5` 也拼成 token。

        干净对照（同一引擎、只差声明）：未声明 `digit_separator` 时两者都在 `'` 处断开
        （`_run("1.'5", C_CFG_NO_SEP) == "1."`）——即"宽进"是声明带来的，不是引擎本来如此。
        """
        assert _run("0x'1") == "0x'1"
        assert _run("1.'5") == "1.'5"
        assert _run("1.'5", C_CFG_NO_SEP) == "1."
