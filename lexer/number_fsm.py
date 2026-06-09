"""
有限状态机驱动的数字字面量解析器（配置表版本）。

使用通用 FSM 引擎 + 转移表，易于维护和扩展。
所有测试通过。
"""

from typing import Dict, Tuple, Set, Callable, Optional

# ============================================================================
# 通用 FSM 引擎
# ============================================================================


class GenericFSM:
    """通用的确定性有限状态自动机（提供转移查询）"""

    def __init__(
        self,
        transitions: Dict[Tuple[int, str], int],
        category_func: Callable[[str], Optional[str]],
        accepting_states: Set[int],
    ):
        self.transitions = transitions
        self.category_func = category_func
        self.accepting = accepting_states

    def next_state(self, state: int, ch: str) -> Optional[int]:
        cat = self.category_func(ch)
        if cat is None:
            return None
        return self.transitions.get((state, cat))


# ============================================================================
# 数字解析器的状态定义和转移配置
# ============================================================================


class NumberFSM:
    # 状态常量
    (
        DEC_INT,  # 十进制整数
        LEADING_ZERO,  # 前导 0
        FRACTION,  # 刚看到小数点
        FRAC_DIGIT,  # 小数部分数字
        EXP,  # 刚看到 e/E
        EXP_SIGN,  # 指数符号
        EXP_DIGIT,  # 指数部分数字
        HEX,  # 十六进制数字（0x 之后）
        BIN,  # 二进制数字（0b 之后）
        OCT,  # 八进制数字（0o 之后）
        AFTER_QUOTE,  # Verilog 位宽数字后的 '
        VERILOG_DEC_VALUE,  # Verilog 'd 之后的十进制数字
        VERILOG_BIN_VALUE,  # Verilog 'b 之后的二进制数字
        VERILOG_HEX_VALUE,  # Verilog 'h 之后的十六进制数字
        VERILOG_OCT_VALUE,  # Verilog 'o 之后的八进制数字
    ) = range(15)

    # 接受状态集合
    _ACCEPTING = {
        DEC_INT,
        LEADING_ZERO,
        FRACTION,
        FRAC_DIGIT,
        EXP_DIGIT,
        HEX,
        BIN,
        OCT,
        VERILOG_DEC_VALUE,
        VERILOG_BIN_VALUE,
        VERILOG_HEX_VALUE,
        VERILOG_OCT_VALUE,
    }

    # 字符→类别映射表（细粒度类别，不含重复自身的条目）
    _CHAR_CATEGORY = {
        # 数字（按优先级：bin > oct > digit）
        "0": "bin_digit",
        "1": "bin_digit",
        "2": "oct_digit",
        "3": "oct_digit",
        "4": "oct_digit",
        "5": "oct_digit",
        "6": "oct_digit",
        "7": "oct_digit",
        "8": "digit",
        "9": "digit",
        # 字母类别名本身就是返回值，无需单独维护
        "e": "eE",
        "E": "eE",
        "+": "sign",
        "-": "sign",
        "x": "xX",
        "X": "xX",
        "b": "bB",
        "B": "bB",
        "o": "oO",
        "O": "oO",
        "d": "dD",
        "D": "dD",
        "h": "hH",
        "H": "hH",
        # 符号
        ".": "dot",
        "'": "quote",
        "_": "underscore",
        # hex_letter：排除了已有独立类别的 a/b/c/d/e/f → 只剩 a/c/f
        "a": "hex_letter",
        "c": "hex_letter",
        "f": "hex_letter",
        "A": "hex_letter",
        "C": "hex_letter",
        "F": "hex_letter",
    }

    @staticmethod
    def _char_category(ch: str) -> Optional[str]:
        return NumberFSM._CHAR_CATEGORY.get(ch)

    # 转移表
    _TRANSITIONS = {
        # DEC_INT
        (DEC_INT, "digit"): DEC_INT,
        (DEC_INT, "bin_digit"): DEC_INT,
        (DEC_INT, "oct_digit"): DEC_INT,
        (DEC_INT, "underscore"): DEC_INT,
        (DEC_INT, "dot"): FRACTION,
        (DEC_INT, "eE"): EXP,
        (DEC_INT, "quote"): AFTER_QUOTE,
        # LEADING_ZERO
        (LEADING_ZERO, "digit"): DEC_INT,
        (LEADING_ZERO, "bin_digit"): DEC_INT,
        (LEADING_ZERO, "oct_digit"): DEC_INT,
        (LEADING_ZERO, "underscore"): DEC_INT,
        (LEADING_ZERO, "dot"): FRACTION,
        (LEADING_ZERO, "eE"): EXP,
        (LEADING_ZERO, "xX"): HEX,
        (LEADING_ZERO, "bB"): BIN,
        (LEADING_ZERO, "oO"): OCT,
        (LEADING_ZERO, "quote"): AFTER_QUOTE,
        # FRACTION
        (FRACTION, "digit"): FRAC_DIGIT,
        (FRACTION, "bin_digit"): FRAC_DIGIT,
        (FRACTION, "oct_digit"): FRAC_DIGIT,
        # FRAC_DIGIT
        (FRAC_DIGIT, "digit"): FRAC_DIGIT,
        (FRAC_DIGIT, "bin_digit"): FRAC_DIGIT,
        (FRAC_DIGIT, "oct_digit"): FRAC_DIGIT,
        (FRAC_DIGIT, "underscore"): FRAC_DIGIT,
        (FRAC_DIGIT, "eE"): EXP,
        # EXP
        (EXP, "digit"): EXP_DIGIT,
        (EXP, "bin_digit"): EXP_DIGIT,
        (EXP, "oct_digit"): EXP_DIGIT,
        (EXP, "sign"): EXP_SIGN,
        # EXP_SIGN
        (EXP_SIGN, "digit"): EXP_DIGIT,
        (EXP_SIGN, "bin_digit"): EXP_DIGIT,
        (EXP_SIGN, "oct_digit"): EXP_DIGIT,
        # EXP_DIGIT
        (EXP_DIGIT, "digit"): EXP_DIGIT,
        (EXP_DIGIT, "bin_digit"): EXP_DIGIT,
        (EXP_DIGIT, "oct_digit"): EXP_DIGIT,
        (EXP_DIGIT, "underscore"): EXP_DIGIT,
        # HEX（合法十六进制字符：0-9, a-f, A-F + 下划线）
        (HEX, "digit"): HEX,
        (HEX, "bin_digit"): HEX,
        (HEX, "oct_digit"): HEX,
        (HEX, "hex_letter"): HEX,
        (HEX, "bB"): HEX,  # b=11
        (HEX, "dD"): HEX,  # d=13
        (HEX, "eE"): HEX,  # e=14
        (HEX, "underscore"): HEX,
        # BIN
        (BIN, "bin_digit"): BIN,
        (BIN, "underscore"): BIN,
        # OCT
        (OCT, "oct_digit"): OCT,
        (OCT, "underscore"): OCT,
        # AFTER_QUOTE
        (AFTER_QUOTE, "dD"): VERILOG_DEC_VALUE,
        (AFTER_QUOTE, "bB"): VERILOG_BIN_VALUE,
        (AFTER_QUOTE, "hH"): VERILOG_HEX_VALUE,
        (AFTER_QUOTE, "oO"): VERILOG_OCT_VALUE,
        # VERILOG_DEC_VALUE
        (VERILOG_DEC_VALUE, "digit"): VERILOG_DEC_VALUE,
        (VERILOG_DEC_VALUE, "bin_digit"): VERILOG_DEC_VALUE,
        (VERILOG_DEC_VALUE, "oct_digit"): VERILOG_DEC_VALUE,
        (VERILOG_DEC_VALUE, "underscore"): VERILOG_DEC_VALUE,
        # VERILOG_BIN_VALUE
        (VERILOG_BIN_VALUE, "bin_digit"): VERILOG_BIN_VALUE,
        (VERILOG_BIN_VALUE, "underscore"): VERILOG_BIN_VALUE,
        # VERILOG_HEX_VALUE（合法十六进制字符：0-9, a-f, A-F + 下划线）
        (VERILOG_HEX_VALUE, "digit"): VERILOG_HEX_VALUE,
        (VERILOG_HEX_VALUE, "bin_digit"): VERILOG_HEX_VALUE,
        (VERILOG_HEX_VALUE, "oct_digit"): VERILOG_HEX_VALUE,
        (VERILOG_HEX_VALUE, "hex_letter"): VERILOG_HEX_VALUE,
        (VERILOG_HEX_VALUE, "bB"): VERILOG_HEX_VALUE,  # b=11
        (VERILOG_HEX_VALUE, "dD"): VERILOG_HEX_VALUE,  # d=13
        (VERILOG_HEX_VALUE, "eE"): VERILOG_HEX_VALUE,  # e=14
        (VERILOG_HEX_VALUE, "underscore"): VERILOG_HEX_VALUE,
        # VERILOG_OCT_VALUE
        (VERILOG_OCT_VALUE, "oct_digit"): VERILOG_OCT_VALUE,
        (VERILOG_OCT_VALUE, "underscore"): VERILOG_OCT_VALUE,
    }

    # 类级单例 FSM 引擎实例
    _FSM = GenericFSM(_TRANSITIONS, _char_category, _ACCEPTING)

    @classmethod
    def run(cls, text: str, start_pos: int) -> Tuple[str, int]:
        """从 start_pos 开始解析数字字面量，返回 (token, end_pos)"""
        if start_pos >= len(text):
            return "", start_pos

        first = text[start_pos]
        if first.isdigit():
            init_state = cls.LEADING_ZERO if first == "0" else cls.DEC_INT
            pos = start_pos + 1
        elif first == "'":
            if start_pos + 1 < len(text) and text[start_pos + 1] in "dDbBhHoO":
                init_state = cls.AFTER_QUOTE
                pos = start_pos + 1
            else:
                return "", start_pos
        else:
            return "", start_pos

        fsm = cls._FSM

        state = init_state
        # 初始接受位置：如果初始状态可接受，则至少包含第一个字符
        last_accept = start_pos + 1 if state in cls._ACCEPTING else -1
        prev_underscore = False

        while pos < len(text):
            ch = text[pos]
            # 禁止连续下划线
            if ch == "_" and prev_underscore:
                break
            nxt = fsm.next_state(state, ch)
            if nxt is None:
                break
            state = nxt
            prev_underscore = ch == "_"
            pos += 1
            if state in cls._ACCEPTING:
                last_accept = pos

        if last_accept > start_pos:
            token = text[start_pos:last_accept]
            # 去除尾随下划线（下划线只作为内部分隔符）
            trimmed = token.rstrip("_")
            if trimmed:
                return trimmed, start_pos + len(trimmed)
        return "", start_pos

    # 数值范围检测（Verilog 位宽）
    @staticmethod
    def verify_verilog_range(token: str) -> Tuple[bool, Optional[str]]:
        """返回 (是否合法, 错误信息或None)"""
        import re

        m = re.fullmatch(r"(\d+)?'([dDbBhHoO])([0-9a-fA-F]+)", token)
        if not m:
            return True, None
        width_str, base_char, value_str = m.groups()
        base = base_char.lower()
        try:
            if width_str:
                width = int(width_str)
                max_val = (1 << width) - 1
            else:
                # 无位宽时不检查范围
                return True, None

            _BASE_RADIX = {"d": 10, "b": 2, "h": 16, "o": 8}
            radix = _BASE_RADIX.get(base)
            if radix is None:
                return False, f"Unknown base {base}"
            val = int(value_str, radix)

            if val > max_val:
                return False, f"Value {val} exceeds {width}-bit maximum {max_val}"
        except ValueError:
            return False, f"Invalid digit for base {base}"
        return True, None


def _test_fsm():
    cases = [
        ("123", 0, "123", 3, "十进制整数"),
        ("0", 0, "0", 1, "单零"),
        ("456abc", 0, "456", 3, "数字后跟字母"),
        ("3.14", 0, "3.14", 4, "基础浮点"),
        ("3.", 0, "3.", 2, "小数点在末尾"),
        (".5", 0, "", 0, "点开头不是数字"),
        ("1e10", 0, "1e10", 4, "科学计数法"),
        ("2.3e-4", 0, "2.3e-4", 6, "负指数"),
        ("1E+2", 0, "1E+2", 4, "正指数"),
        ("1e", 0, "1", 1, "不完整的指数"),
        ("1e-", 0, "1", 1, "指数符号后无数字"),
        ("0xFF", 0, "0xFF", 4, "十六进制"),
        ("0b1010", 0, "0b1010", 6, "二进制"),
        ("0o755", 0, "0o755", 5, "八进制"),
        ("0b12", 0, "0b1", 3, "二进制遇到非法字符截断"),
        ("0xGG", 0, "0x", 2, "十六进制非法字符（仅前缀）"),
        ("0x", 0, "0x", 2, "十六进制仅有前缀"),
        ("1_000_000", 0, "1_000_000", 9, "带下划线的十进制"),
        ("0xFF_FF", 0, "0xFF_FF", 7, "带下划线的十六进制"),
        ("0b1010_1010", 0, "0b1010_1010", 11, "带下划线的二进制"),
        ("1_", 0, "1", 1, "下划线结尾截断"),
        ("1__2", 0, "1", 1, "连续下划线截断"),
        ("_100", 0, "", 0, "下划线开头不是数字"),
        ("32'd0", 0, "32'd0", 5, "Verilog 十进制位宽"),
        ("1'b0", 0, "1'b0", 4, "Verilog 二进制位宽"),
        ("8'ha3", 0, "8'ha3", 5, "Verilog 十六进制位宽"),
        ("32'd", 0, "32'd", 4, "Verilog 无数值（仅前缀）"),
        ("0'd0", 0, "0'd0", 4, "Verilog 零位宽"),
        ("8'daa", 0, "8'd", 3, "十进制遇到 a 截断"),
        ("4'b102", 0, "4'b10", 5, "二进制遇到 2 截断"),
        ("8'hoG", 0, "8'h", 3, "十六进制遇到 o 截断"),
        ("6'o78", 0, "6'o7", 4, "八进制遇到 8 截断"),
        ("'b1", 0, "'b1", 3, "无位宽二进制"),
        ("'d0", 0, "'d0", 3, "无位宽十进制"),
        ("'hFF", 0, "'hFF", 4, "无位宽十六进制"),
        ("'o7", 0, "'o7", 3, "无位宽八进制"),
        ("'b1010", 0, "'b1010", 6, "无位宽二进制多值"),
        ("'hdead", 0, "'hdead", 6, "无位宽十六进制多值"),
        ("'b", 0, "'b", 2, "无位宽无数值（仅前缀）"),
        ("'x1", 0, "", 0, "非法基数应拒绝"),
        ("'", 0, "", 0, "孤立的 ' 应拒绝"),
        ("", 0, "", 0, "空字符串"),
        ("abc", 0, "", 0, "非数字开头"),
        ("123+456", 0, "123", 3, "遇到符号截断"),
        ("123 )", 0, "123", 3, "遇到括号截断"),
        ("0x0B", 0, "0x0B", 4, "0x 后跟 0B（合法十六进制）"),
        ("1.2.3", 0, "1.2", 3, "多点截断"),
        ("3.14abc", 0, "3.14", 4, "浮点后跟字母截断"),
        ("1e10_000", 0, "1e10_000", 8, "指数部分带下划线"),
    ]

    all_pass = True
    for input_str, start, expected_val, expected_end, desc in cases:
        val, end = NumberFSM.run(input_str, start)
        if val != expected_val or end != expected_end:
            print(
                f"FAIL [{desc}]: '{input_str}'[{start}:] → '{val}'({end}), expected '{expected_val}'({expected_end})"
            )
            all_pass = False

    if all_pass:
        print("✅ 所有数字 FSM 测试通过!")
    else:
        print("❌ 存在失败的测试用例")

    # 测试数值范围检测
    print("\n--- 数值范围检测测试 ---")
    range_cases = [
        ("8'hFF", True, None),
        ("8'h100", False, "exceeds"),
        ("4'b1111", True, None),
        ("4'b10000", False, "exceeds"),
        ("32'd4294967295", True, None),
        ("32'd4294967296", False, "exceeds"),
        ("'hFF", True, None),
    ]
    for token, expect_ok, expect_msg_part in range_cases:
        ok, err = NumberFSM.verify_verilog_range(token)
        if ok != expect_ok or (err is not None and expect_msg_part not in err):
            print(f"FAIL range: {token} -> ok={ok}, err={err}")
        else:
            print(f"PASS range: {token}")


def _test_interactive():
    print("\n交互式测试模式（输入空行退出）：")
    while True:
        line = input(">> ")
        if not line:
            break
        val, end = NumberFSM.run(line, 0)
        remain = line[end:]
        print(f"  Parsed: '{val}'  |  Remaining: '{remain}'")
        ok, err = NumberFSM.verify_verilog_range(val)
        if not ok:
            print(f"  ⚠️  Warning: {err}")


if __name__ == "__main__":
    _test_fsm()
    # _test_interactive()
