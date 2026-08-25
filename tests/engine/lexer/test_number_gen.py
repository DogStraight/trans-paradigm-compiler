"""number_gen 生成器测试 — 声明 → FSM 转移表 → 可解析数字。

验证编译器的正确性：给定声明，生成的 FSM 能正确接受/拒绝数字形态。
（生成器已接入 number_runner；本文件专注声明 → 转移表的编译语义。）
"""

import pytest

from lexer.number_gen import compile_patterns, char_category


class _Runner:
    """把 NumberPattern 当通用 FSM 跑：state 编号在 pattern 内独立。

    run(text, pos) → (token, end_pos)：从 start 走转移，返回最长接受。
    """

    def __init__(self, patterns):
        self.patterns = patterns

    def run(self, text: str, pos: int) -> tuple[str, int]:
        best = ("", pos)
        for pat in self.patterns:
            state = pat.start_state
            last_accept = pos
            # 起始字符必须能走第一步（start 的转移）
            i = pos
            prev_us = False
            while i < len(text):
                ch = text[i]
                if ch == "_" and prev_us:
                    break
                cat = char_category(ch)
                nxt = None
                if cat:
                    nxt = pat.transitions.get((state, cat))
                if nxt is None:
                    break
                state = nxt
                prev_us = ch == "_"
                i += 1
                if state in pat.accepting:
                    last_accept = i
            if last_accept > pos:
                tok = text[pos:last_accept].rstrip("_")
                if tok and len(tok) > len(best[0]):
                    best = (tok, pos + len(tok))
        return best


# 简单 Verilog 声明（对照配置化 runner 的行为基线）
VERILOG_CFG = [
    {
        "name": "verilog_width",
        "size": {"digits": "nonzero"},
        "base_prefix": "'",
        "bases": ["d", "b", "o", "h"],
        "value_digits": {"d": "dec", "b": "bin", "o": "oct", "h": "hex"},
        "value_allow": ["x", "z", "?"],
    },
    {
        # 无 size 形态：'d42 / 'hff
        "name": "verilog_unsized",
        "size": "none",
        "base_prefix": "'",
        "bases": ["d", "b", "o", "h"],
        "value_digits": {"d": "dec", "b": "bin", "o": "oct", "h": "hex"},
        "value_allow": ["x", "z", "?"],
    },
]


@pytest.fixture(scope="module")
def vrun():
    pats = compile_patterns(VERILOG_CFG)
    return _Runner(pats)


class TestGenVerilogWidth:
    """生成 FSM 解析 Verilog 位宽数字。"""

    @pytest.mark.parametrize(
        "src,expected",
        [
            ("8'hff", "8'hff"),
            ("16'd1000", "16'd1000"),
            ("4'b1010", "4'b1010"),
            ("4'b1x0z", "4'b1x0z"),
            ("8'dx", "8'dx"),
            ("32'bx", "32'bx"),
            ("4'b1?0", "4'b1?0"),
            ("'d42", "'d42"),      # 无 size
            ("'hff", "'hff"),
        ],
    )
    def test_accept(self, vrun, src, expected):
        tok, _ = vrun.run(src, 0)
        assert tok == expected, f"{src!r} → {tok!r}"

    @pytest.mark.parametrize(
        "src",
        [
            "8'h",       # 无 value
            "8'hff+",    # 后续符号不并入
        ],
    )
    def test_partial(self, vrun, src):
        """不完整/后续 → 吃有效前缀。"""
        tok, _ = vrun.run(src, 0)
        assert tok, f"{src!r} 应吃到有效前缀"

    def test_incomplete_no_base(self, vrun):
        """8'（有 size 无 base）→ 吃有效前缀 8（size 态是接受态，十进制整数）。"""
        tok, _ = vrun.run("8'", 0)
        assert tok == "8"


class TestGenMultiCharPrefix:
    """多字符前缀：每条前缀独立建链，值随前缀。

    回归：曾只建同首字符组的第一条链（plist[0][1:]），且 value 进制只取
    第一个——0x|0b 声明下 0b101 只能吃到 0。
    """

    MULTI_CFG = [
        {
            "name": "c_prefix",
            "size": "none",
            "base_prefix": "0x|0b",
            "bases": [],
            "value_digits": {"x": "hex", "b": "bin"},
            "value_allow": [],
        },
    ]

    @pytest.fixture(scope="class")
    def mrun(self):
        pats = compile_patterns(self.MULTI_CFG)
        return _Runner(pats)

    @pytest.mark.parametrize(
        "src,expected",
        [
            ("0x1F", "0x1F"),   # hex 链
            ("0b101", "0b101"), # bin 链（回归：曾只吃 0）
            ("0x", "0x"),       # hex value 空 → 前缀本身
            ("0b", "0b"),       # bin value 空 → 前缀本身
            ("0o17", ""),       # 0o 未声明 → 无匹配
        ],
    )
    def test_multi(self, mrun, src, expected):
        tok, _ = mrun.run(src, 0)
        assert tok == expected, f"{src!r} → {tok!r}"

    def test_value_radix_follows_prefix(self, mrun):
        """0b 后只认 bin digit：0b12 的 2 不并入（bin 无 digit2）。"""
        tok, _ = mrun.run("0b12", 0)
        assert tok == "0b1", f"0b12 → {tok!r}"
        # 0x 后只认 hex digit：0x1g 的 g 不并入
        tok, _ = mrun.run("0x1g", 0)
        assert tok == "0x1", f"0x1g → {tok!r}"
