"""数字字面量测试基线 — 固化完整 token 序列 + content（不只 type）。

P2.1 数字形态配置化已完成：
  - 现状 tests/lexer 的数字测试曾只断言 type 不断言 content/token 数，
    存在假阳性（如 test_signed_literal 只查 token[0].type 是 number）。
  - 本文件按语言固化「完整 token 序列 + content」，作为配置驱动数字
    （number_gen + number_runner）的回归基线（旧 NumberFSM 回退已移除）。

标注：
  - ✅ 期望正确行为（配置驱动路径须保持）
  - 🐛 已知缺陷（当前行为按实际断言）
"""

import pytest

# ═══════════════════════════════════════════════════════
# 十进制整数 / 浮点 / 科学计数（Verilog + C 共用形态）
# ═══════════════════════════════════════════════════════


class TestBaselineDecFloat:
    """十进制整数 / 浮点 / 科学计数 — 完整 token 序列 + content。"""

    @pytest.mark.parametrize(
        "src,expected",
        [
            # (输入, 期望 content 序列)
            ("42", ["42"]),
            ("0", ["0"]),
            ("3.14", ["3.14"]),
            ("1e10", ["1e10"]),
            ("2.3e-4", ["2.3e-4"]),
            ("1E+2", ["1E+2"]),
            # 完整 token 序列（不只 content）：数字后跟标识符 → 数字 + id
            ("456abc", ["456", "abc"]),
            ("42 3.14 8'hff", ["42", "3.14", "8'hff"]),
            ("1_000", ["1_000"]),
        ],
    )
    def test_content_sequence(self, lexer, src, expected):
        tokens = lexer.tokenize(src)
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == expected, f"{src!r} → {contents!r}"

    def test_underscore_behavior(self, lexer):
        """下划线行为：1__2 连续下划线 → 1 是数字、__2 是 id；_1 开头不是数字。"""
        # 连续下划线：1__2 → 1（数字）+ __2（id）
        tokens = lexer.tokenize("1__2")
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == ["1", "__2"], f"1__2 → {contents!r}"
        # 下划线开头不是数字
        tokens = lexer.tokenize("_1")
        assert tokens[0].type != "literal.number"


# ═══════════════════════════════════════════════════════
# Verilog 位宽数字（[size]'[s]base value）
# ═══════════════════════════════════════════════════════


class TestBaselineVerilogWidth:
    """Verilog 位宽数字 — 完整 token 序列 + content。"""

    @pytest.mark.parametrize(
        "src,expected",
        [
            ("8'hff", ["8'hff"]),
            ("16'd1000", ["16'd1000"]),
            ("4'b1010", ["4'b1010"]),
            ("4'b1x0z", ["4'b1x0z"]),  # x/z 是合法基值
            ("8'dx", ["8'dx"]),
            ("32'bx", ["32'bx"]),
            ("4'b1?0", ["4'b1?0"]),  # ? 紧跟数字是基值
            ("8'ho", ["8'h", "o"]),  # o 在 'h 后不是合法 digit → 切分（当前行为）
            ("32'h ffff_ffff", ["32'h ffff_ffff"]),  # 'h 后允许空格
            ("32'h x", ["32'h x"]),  # 跨空格 x 仍合法
            # 无位宽形态
            ("'d42", ["'d42"]),
            ("'hff", ["'hff"]),
        ],
    )
    def test_content_sequence(self, lexer, src, expected):
        tokens = lexer.tokenize(src)
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == expected, f"{src!r} → {contents!r}"

    @pytest.mark.parametrize(
        "src,expected",
        [
            # 跨空格 ? 是三元运算符而非基值：2'b00 ? a : b
            ("2'b00 ? a : b", ["2'b00", "?", "a", ":", "b"]),
            # 位宽后跟运算符
            ("8'hff + 1", ["8'hff", "+", "1"]),
            # 位宽后跟字母被并入（当前行为：VERILOG_HEX_VALUE 接受 hex_letter）
            ("8'hffabc", ["8'hffabc"]),
        ],
    )
    def test_sequence_with_following(self, lexer, src, expected):
        """位宽数字与后续 token 的正确切分（不只数字本身）。"""
        tokens = lexer.tokenize(src)
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == expected, f"{src!r} → {contents!r}"


class TestBaselineSignedKnownBug:
    """signed 位宽 's — 已修复（配置驱动生成 FSM 支持 's 链）。"""

    def test_signed_literal_fixed(self, lexer):
        """✅ 16'sd100 现在为单 token（'s 链：' → s → d → value）。"""
        tokens = lexer.tokenize("16'sd100")
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == ["16'sd100"], f"16'sd100 → {contents!r}"

    def test_signed_binary_fixed(self, lexer):
        """✅ 8'sb1010 单 token（signed 二进制）。"""
        tokens = lexer.tokenize("8'sb1010")
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == ["8'sb1010"], f"8'sb1010 → {contents!r}"

    def test_leading_zero_width_rejected(self, lexer):
        """✅ 0'b1 被拒绝为位宽数字（标准 A.8.7：size = non_zero_unsigned_number，
        必须以 1-9 开头）。0 是合法 unsigned_number，'b1 是 unsized——切为两个 token。"""
        tokens = lexer.tokenize("0'b1")
        contents = [t.content for t in tokens if t.type != "space.indent"]
        assert contents == ["0", "'b1"], f"0'b1 → {contents!r}（size 非零开头）"


class TestBaselineUnsupported:
    """当前不支持 / 不属于数字的形态 — 防御性断言。"""

    def test_dot_leading_not_number(self, lexer):
        """.5 点开头不是数字。"""
        tokens = lexer.tokenize(".5")
        assert tokens[0].type != "literal.number"

    def test_incomplete_exponent(self, lexer):
        """1e / 1e- 不完整指数 → 1 是数字、e/e/- 后续分别 token。"""
        for src, exp in [("1e", ["1", "e"]), ("1e-", ["1", "e", "-"])]:
            tokens = lexer.tokenize(src)
            contents = [t.content for t in tokens if t.type != "space.indent"]
            assert contents == exp, f"{src!r} → {contents!r}"
