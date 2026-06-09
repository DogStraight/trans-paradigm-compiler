"""
有限状态机驱动的数字字面量解析器。

替代了原先 main_lexer.py 中靠 while + 终止符集合"瞎吃"的方式，
改为显式的状态转移图，每个字符只处理一次，无回溯，支持最长匹配。

支持的格式：
- 十进制整数：123
- 浮点数：3.14, 3.
- 科学计数法：1e10, 2.3e-4, 1E10
- 十六进制：0xFF, 0XFF
- 二进制：0b1010, 0B1010
- 八进制：0o755, 0O755
- 下划线分隔：1_000_000, 0xFF_FF
- Verilog 位宽字面量：32'd0, 8'ha3, 1'b0
"""


class NumberFSM:
    """有限状态机驱动的数字字面量解析器"""

    # 状态常量
    (DEC_INT,         # 十进制整数数字（1-9 开头或 0 之后的更多数字）
     LEADING_ZERO,    # 前导 0（刚看到 '0' 时，尚未决定进制）
     FRACTION,        # 刚看到小数点 '.'
     FRAC_DIGIT,      # 小数部分数字
     EXP,             # 刚看到 e/E，期待符号或数字
     EXP_SIGN,        # 指数符号 +/-
     EXP_DIGIT,       # 指数部分数字
     HEX,             # 十六进制数字（0x 之后）
     BIN,             # 二进制数字（0b 之后）
     OCT,             # 八进制数字（0o 之后）
     AFTER_QUOTE,     # Verilog 位宽数字后的 '
     VERILOG_VALUE,   # Verilog 基数后的数值部分
    ) = range(12)

    # 可接受状态——状态机在此停下时可作为有效数字返回
    _ACCEPTING = {
        DEC_INT, LEADING_ZERO, FRACTION, FRAC_DIGIT,
        EXP_DIGIT, HEX, BIN, OCT, VERILOG_VALUE,
    }

    @classmethod
    def run(cls, text: str, start_pos: int) -> tuple[str, int]:
        """
        从 start_pos 开始解析数字字面量。

        Args:
            text: 源文本
            start_pos: 起始位置（必须指向数字字符，否则返回空）

        Returns:
            (content, end_pos): 解析到的内容和结束位置（不含）
            如果无法形成有效数字，返回 ("", start_pos)
        """
        if start_pos >= len(text) or not text[start_pos].isdigit():
            return ("", start_pos)

        # 初始状态：根据第一个字符确定
        first = text[start_pos]
        state = cls.LEADING_ZERO if first == '0' else cls.DEC_INT

        last_accept = start_pos + 1 if state in cls._ACCEPTING else -1
        pos = start_pos + 1

        while pos < len(text):
            ch = text[pos]
            next_ch = text[pos + 1] if pos + 1 < len(text) else ''

            next_state = cls._transition(state, ch, next_ch)
            if next_state is None:
                break

            state = next_state
            pos += 1
            if state in cls._ACCEPTING:
                last_accept = pos

        if last_accept >= start_pos:
            return (text[start_pos:last_accept], last_accept)
        return ("", start_pos)

    @classmethod
    def _transition(cls, state: int, ch: str, next_ch: str) -> int | None:
        """状态转移函数。返回下一状态，None 表示不接受此字符。"""

        # ---------- 十进制整数 ----------
        if state == cls.DEC_INT:
            if ch.isdigit():
                return cls.DEC_INT
            if ch == '_' and next_ch.isdigit():
                return cls.DEC_INT
            if ch == '.':
                return cls.FRACTION
            if ch in 'eE':
                return cls.EXP
            if ch == "'":
                return cls.AFTER_QUOTE
            return None

        # ---------- 前导零 ----------
        if state == cls.LEADING_ZERO:
            if ch in 'xX':
                return cls.HEX
            if ch in 'bB':
                return cls.BIN
            if ch in 'oO':
                return cls.OCT
            if ch.isdigit():
                return cls.DEC_INT
            if ch == '_' and next_ch.isdigit():
                return cls.DEC_INT
            if ch == '.':
                return cls.FRACTION
            if ch in 'eE':
                return cls.EXP
            if ch == "'":
                return cls.AFTER_QUOTE
            return None

        # ---------- 刚看到小数点 ----------
        if state == cls.FRACTION:
            if ch.isdigit():
                return cls.FRAC_DIGIT
            # 小数点后无数字不合法（拒绝），但 FRACTION 自身是接受态
            return None

        # ---------- 小数部分数字 ----------
        if state == cls.FRAC_DIGIT:
            if ch.isdigit():
                return cls.FRAC_DIGIT
            if ch == '_' and next_ch.isdigit():
                return cls.FRAC_DIGIT
            if ch in 'eE':
                return cls.EXP
            return None

        # ---------- 指数标记 e/E ----------
        if state == cls.EXP:
            if ch in '+-':
                return cls.EXP_SIGN
            if ch.isdigit():
                return cls.EXP_DIGIT
            return None

        # ---------- 指数符号 ----------
        if state == cls.EXP_SIGN:
            if ch.isdigit():
                return cls.EXP_DIGIT
            return None

        # ---------- 指数部分数字 ----------
        if state == cls.EXP_DIGIT:
            if ch.isdigit():
                return cls.EXP_DIGIT
            if ch == '_' and next_ch.isdigit():
                return cls.EXP_DIGIT
            return None

        # ---------- 十六进制 ----------
        if state == cls.HEX:
            if ch.isdigit() or ch in 'abcdefABCDEF':
                return cls.HEX
            if ch == '_' and (next_ch.isdigit() or next_ch in 'abcdefABCDEF'):
                return cls.HEX
            return None

        # ---------- 二进制 ----------
        if state == cls.BIN:
            if ch in '01':
                return cls.BIN
            if ch == '_' and next_ch in '01':
                return cls.BIN
            return None

        # ---------- 八进制 ----------
        if state == cls.OCT:
            if ch in '01234567':
                return cls.OCT
            if ch == '_' and next_ch in '01234567':
                return cls.OCT
            return None

        # ---------- Verilog ' 之后期待基数 ----------
        if state == cls.AFTER_QUOTE:
            if ch in 'dDbBhHoO':
                return cls.VERILOG_VALUE
            return None

        # ---------- Verilog 基数后的数值 ----------
        if state == cls.VERILOG_VALUE:
            if ch.isdigit() or ch in 'abcdefABCDEF':
                return cls.VERILOG_VALUE
            if ch == '_' and (next_ch.isdigit() or next_ch in 'abcdefABCDEF'):
                return cls.VERILOG_VALUE
            return None

        return None


# ===========================================================================
# 测试
# ===========================================================================

def _test_fsm():
    """运行 NumberFSM 的单元测试"""
    cases = [
        # (输入, 起始位置, 期望结果, 期望结束位置, 说明)
        # --- 基本数字 ---
        ("123",     0, "123",     3, "十进制整数"),
        ("0",       0, "0",       1, "单零"),
        ("456abc",  0, "456",     3, "数字后跟字母"),
        # --- 浮点数 ---
        ("3.14",    0, "3.14",    4, "基础浮点"),
        ("3.",      0, "3.",      2, "小数点在末尾（Python 合法）"),
        (".5",      0, "",        0, "点开头不是数字"),
        # --- 科学计数法 ---
        ("1e10",    0, "1e10",    4, "科学计数法"),
        ("2.3e-4",  0, "2.3e-4",  6, "负指数"),
        ("1E+2",    0, "1E+2",    4, "正指数"),
        ("1e",      0, "1",       1, "不完整的指数"),
        ("1e-",     0, "1",       1, "指数符号后无数字"),
        # --- 进制前缀 ---
        ("0xFF",    0, "0xFF",    4, "十六进制"),
        ("0b1010",  0, "0b1010",  6, "二进制"),
        ("0o755",   0, "0o755",   5, "八进制"),
        ("0b12",    0, "0b1",     3, "二进制遇到非法字符截断"),
        ("0xGG",    0, "0x",      2, "十六进制非法字符（仅前缀）"),
        ("0x",      0, "0x",      2, "十六进制仅有前缀"),
        # --- 下划线分隔 ---
        ("1_000_000",  0, "1_000_000",  9, "带下划线的十进制"),
        ("0xFF_FF",    0, "0xFF_FF",    7, "带下划线的十六进制"),
        ("0b1010_1010", 0, "0b1010_1010", 11, "带下划线的二进制"),
        ("1_",      0, "1",       1, "下划线结尾截断"),
        ("1__2",    0, "1",       1, "连续下划线截断"),
        ("_100",    0, "",        0, "下划线开头不是数字"),
        # --- Verilog 位宽 ---
        ("32'd0",   0, "32'd0",   5, "Verilog 十进制位宽"),
        ("1'b0",    0, "1'b0",    4, "Verilog 二进制位宽"),
        ("8'ha3",   0, "8'ha3",   5, "Verilog 十六进制位宽"),
        ("32'd",    0, "32'd",    4, "Verilog 无数值（仅前缀，合法但值为空?）"),
        ("0'd0",    0, "0'd0",    4, "Verilog 零位宽"),
        # --- 边界 ---
        ("",        0, "",        0, "空字符串"),
        ("abc",     0, "",        0, "非数字开头"),
        ("123+456", 0, "123",     3, "遇到符号截断"),
        ("123 )",   0, "123",     3, "遇到括号截断"),
        ("0x0B",    0, "0x0B",    4, "0x 后跟 0B（合法十六进制）"),
        # --- 复合场景 ---
        ("1.2.3",   0, "1.2",     3, "多点截断（第一个小数点合法）"),
        ("3.14abc", 0, "3.14",    4, "浮点后跟字母截断"),
        ("1e10_000", 0, "1e10_000", 8, "指数部分带下划线"),
    ]

    all_pass = True
    for input_str, start, expected_val, expected_end, desc in cases:
        val, end = NumberFSM.run(input_str, start)
        if val != expected_val or end != expected_end:
            print(
                f"FAIL [{desc}]: "
                f"'{input_str}'[{start}:] → '{val}'({end}), "
                f"expected '{expected_val}'({expected_end})"
            )
            all_pass = False

    if all_pass:
        print("✅ 所有数字 FSM 测试通过!")
    else:
        print("❌ 存在失败的测试用例")


def _test_interactive():
    """交互式测试：可手动输入查看解析结果"""
    print("\n交互式测试模式（输入空行退出）：")
    while True:
        line = input(">> ")
        if not line:
            break
        val, end = NumberFSM.run(line, 0)
        remain = line[end:]
        print(f"  Parsed: '{val}'  |  Remaining: '{remain}'")


if __name__ == "__main__":
    _test_fsm()
    _test_interactive()
