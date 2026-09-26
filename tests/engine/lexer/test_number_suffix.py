"""字面量**尾随后缀**（`[[number.based]] suffix` 键）测试。

背景：C99 的整型/浮点后缀（`42u` / `1ULL` / `0x1Fu` / `1.5f`）此前表达不了——
`[[number.based]]` 没有后缀位，`42u` 被切成 `42` + `u`。后缀做成**DFA 之后的
声明式尾段**（由 `number_runner` 消费），不是 DFA 转移：字符→类别映射是**全局**的，
而 `f`/`F` 已是十六进制 digit 类别（`hex_value_abc`），按类别加后缀边会与 hex 值
自环**撞键**（覆盖后十六进制数字解析崩）。本文件用 `0x1FF` 把这条判据钉死。

Doc: docs/gaps/gap-language-pack-scope.md（C 包词法面）
"""

import pytest

from core.errors import ConfigError
from lexer.number_gen import compile_number_pattern, compile_patterns
from lexer.number_runner import build_number_runner

# C 风格三形态（照 grammar/c/base/_number.toml 的最小复现）
C_CFG = [
    {
        "name": "c_prefix",
        "size": "none",
        "base_prefix": "0x",
        "bases": [],
        "value_digits": {"x": "hex"},
        "value_allow": [],
        "suffix": {"chars": "uUlL", "max": 3},
    },
    {
        "name": "c_dec",
        "size": {"digits": "any"},
        "base_prefix": "none",
        "bases": [],
        "value_digits": {"d": "dec"},
        "value_allow": [],
        "suffix": {"chars": "uUlLfF", "max": 3},
    },
]


def _run(src: str, cfgs=C_CFG) -> str:
    runner = build_number_runner(cfgs)
    assert runner is not None
    tok, _ = runner.run(src, 0)
    return tok


class TestSuffixConfig:
    """声明面：读键、默认值、形态非法 fail-fast。"""

    def test_absent_key_means_no_suffix(self):
        pat = compile_number_pattern({"name": "x", "size": "none", "base_prefix": "0x"})
        assert pat.suffix_chars == frozenset()
        assert pat.suffix_max == 0

    def test_chars_and_max_read(self):
        pat = compile_number_pattern(
            {
                "name": "x",
                "size": "none",
                "base_prefix": "0x",
                "suffix": {"chars": "uUlL", "max": 2},
            }
        )
        assert pat.suffix_chars == frozenset("uUlL")
        assert pat.suffix_max == 2

    def test_chars_list_and_default_max(self):
        """`chars` 允许列表写法；不写 `max` 时默认 = 字符集大小。"""
        pat = compile_number_pattern(
            {
                "name": "x",
                "size": "none",
                "base_prefix": "0x",
                "suffix": {"chars": ["u", "U"]},
            }
        )
        assert pat.suffix_chars == frozenset("uU")
        assert pat.suffix_max == 2

    @pytest.mark.parametrize(
        "suffix",
        [
            "uUlL",                       # 不是表
            {},                           # 缺 chars
            {"chars": ""},                # 空字符集
            {"chars": "uU", "max": 0},    # 长度上限 < 1
            {"chars": "uU", "max": "2"},  # max 类型错
            {"chars": "uU", "max": True}, # bool 不是整数
        ],
    )
    def test_malformed_suffix_fails_fast(self, suffix):
        """后缀声明写错 → 直接报错（不静默降级成"无后缀"）。"""
        with pytest.raises(ConfigError):
            compile_number_pattern(
                {
                    "name": "x",
                    "size": "none",
                    "base_prefix": "0x",
                    "suffix": suffix,
                }
            )


class TestLeadDotConfig:
    """`lead_dot` 键（前导点浮点 `.5`）的声明面。"""

    def test_absent_key_means_no_lead_dot(self):
        pat = compile_number_pattern({"name": "x", "size": "none", "base_prefix": "0x"})
        assert pat.lead_dot is False

    def test_lead_dot_flag_recorded(self):
        pat = compile_number_pattern(
            {"name": "x", "size": "none", "base_prefix": "none", "lead_dot": True}
        )
        assert pat.lead_dot is True

    @pytest.mark.parametrize("bad", ["true", 1, None])
    def test_non_bool_fails_fast(self, bad):
        with pytest.raises(ConfigError):
            compile_number_pattern(
                {"name": "x", "size": "none", "base_prefix": "none", "lead_dot": bad}
            )

    def test_lead_dot_on_prefixed_form_fails_fast(self):
        """有前缀形态里小数点没有"开头"位置 → 声明即错（不静默忽略）。"""
        with pytest.raises(ConfigError):
            compile_number_pattern(
                {
                    "name": "x",
                    "size": "none",
                    "base_prefix": "0x",
                    "value_digits": {"x": "hex"},
                    "lead_dot": True,
                }
            )


class TestLeadDotConsumption:
    """`lead_dot` 的消费面：点后**至少一位**数字；`.` 本身不成为数字。"""

    CFG = [
        {
            "name": "c_dec",
            "size": {"digits": "any"},
            "base_prefix": "none",
            "bases": [],
            "value_digits": {"d": "dec"},
            "value_allow": [],
            "lead_dot": True,
        }
    ]

    def test_leading_dot_float(self):
        assert _run(".5", self.CFG) == ".5"
        assert _run(".25", self.CFG) == ".25"

    def test_leading_dot_with_exponent(self):
        assert _run(".5e3", self.CFG) == ".5e3"
        assert _run(".5E-3", self.CFG) == ".5E-3"

    def test_dot_alone_is_not_a_number(self):
        """**判据样本**：点后无数字 → 不吃（`.` 归符号路径，`a.b` 才不受影响）。"""
        assert _run(".", self.CFG) == ""
        assert _run(".b", self.CFG) == ""

    def test_digits_forms_unchanged(self):
        assert _run("0.5", self.CFG) == "0.5"
        assert _run("5.", self.CFG) == "5."
        assert _run("1e10", self.CFG) == "1e10"

    def test_starts_at_declared_non_digit_is_gated(self):
        """`starts_at_declared_non_digit`：只认**显式声明** lead_dot 的形态。

        ⚠ 反例（引擎实测教训）：若改成"任何声明的起始字符都算"，yaml 的 `-` 前缀
        数字形态会让序列指示符 `- 8080` 的 `-` 变成数字 token（18 处 yaml 测试变红）。
        """
        runner = build_number_runner(self.CFG)
        assert runner is not None
        assert runner.starts_at_declared_non_digit(".5", 0) is True
        assert runner.starts_at_declared_non_digit("-5", 0) is False

        yaml_like = [
            {
                "name": "yaml_neg",
                "size": "none",
                "base_prefix": "-",
                "bases": [],
                "value_digits": {"d": "dec"},
                "value_allow": [],
            }
        ]
        r2 = build_number_runner(yaml_like)
        assert r2 is not None
        assert r2.starts_at_declared_non_digit("-5", 0) is False, (
            "未声明 lead_dot 的形态不得进入'先试数字扫描'（会劫持同字符符号）"
        )


class TestSuffixConsumption:
    """runner 消费：接受位之后按声明集与上限吃后缀。"""

    @pytest.mark.parametrize(
        "src",
        ["42u", "42U", "10L", "10l", "1LL", "1ULL", "1LLU", "1.5f", "1.5F", "1.5L", "1e3L"],
    )
    def test_suffix_merged_into_token(self, src):
        assert _run(src) == src

    def test_hex_digits_then_suffix(self):
        """`0x1Fu`：`F` 由 DFA 当 hex digit 吃掉，`u` 才是后缀。"""
        assert _run("0x1Fu") == "0x1Fu"

    def test_hex_digits_not_broken_by_suffix(self):
        """**撞键判据**：后缀集不含 `fF` 时，`0x1FF` 必须整段吃完。

        若把后缀做成 DFA 转移（按字符类别加边），`hex_value_abc` 的边会被后缀边
        覆盖 → 这里会退化成 `0x1` 或更短。
        """
        assert _run("0x1FF") == "0x1FF"

    def test_max_caps_suffix_length(self):
        """`max` 封顶：`1u2` → `1u`（`2` 留给下一个 token）。"""
        assert _run("1u2") == "1u"

    def test_number_then_identifier_still_splits(self):
        """对照：后缀是**闭集**，真正的标识符不被吞（`456abc` → `456`）。"""
        assert _run("456abc") == "456"

    def test_undeclared_suffix_changes_nothing(self):
        """未声明 suffix 的形态零变化（verilog 的既有行为）。"""
        no_suffix = [
            {
                "name": "verilog_dec",
                "size": {"digits": "nonzero"},
                "base_prefix": "none",
                "bases": [],
                "value_digits": {"d": "dec"},
                "value_allow": [],
            }
        ]
        assert _run("42u", no_suffix) == "42"
        assert _run("42", no_suffix) == "42"

    def test_longest_match_across_patterns_keeps_suffix(self):
        """多形态最长匹配：后缀形态胜出（`patterns` 全量走一遍）。"""
        pats = compile_patterns(C_CFG)
        assert len(pats) == 2
        assert _run("1.5f") == "1.5f"
