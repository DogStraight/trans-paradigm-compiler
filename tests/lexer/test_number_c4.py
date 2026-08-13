"""tests/lexer/test_number_c4.py — c4 数字字面量形态（对齐 c4.c 标准）。

锚点：rswier/c4（github.com/rswier/c4）的 c4.c next() 只支持三种数字形态：
  非零开头十进制（123）、0x/0X 十六进制（0x1F）、前导 0 八进制（017 / 0）。
不支持 0b/0o（C23/Python 风格）——0b101 应拆为 0 + 标识符 b101。

单语言选择模型：fixture 用 load_language("grammar/c4") 初始化 c4 语言包，
测试结束恢复 verilog，避免污染其它测试。
"""

import pytest

from core.config_registry import ConfigRegistry
from lexer import Lexer


@pytest.fixture(scope="module")
def c4_lexer(config_loaded):
    """初始化 c4 语言包，测试结束恢复 verilog。"""
    ConfigRegistry.load_language("grammar/c4")
    lex = Lexer(rules_dir="grammar/c4")
    yield lex
    ConfigRegistry.load_language("grammar/verilog", plugins_dir="grammar/verilog/plugins")


def _contents(tokens):
    return [t.content for t in tokens if t.type != "space.indent"]


class TestC4NumberShapes:
    """c4.c 标准形态 → 完整 token 序列（不只看 type，固化 content）。"""

    @pytest.mark.parametrize(
        "src,expected",
        [
            # 十进制（非零开头）
            ("123", ["123"]),
            ("0", ["0"]),              # 零：由 c_octal（0[0-7]*）提供
            # 十六进制（0x / 0X）
            ("0x1F", ["0x1F"]),
            ("0X1F", ["0X1F"]),
            ("0x", ["0x"]),            # c4.c：0x 后无 digit → 值 0
            # 前导 0 八进制（c4.c else 分支）
            ("017", ["017"]),          # 八进制 15
            ("00", ["00"]),
            # c4.c 不支持的形态：0b/0o → 拆为 0 + 标识符
            ("0b101", ["0", "b101"]),
            ("0o17", ["0", "o17"]),
            # 8/9 不是八进制 digit：08 → 0 + 8（c4.c 同，8 另起 token）
            ("08", ["0", "8"]),
            ("0x1G", ["0x1", "G"]),    # G 不是 hex digit
        ],
    )
    def test_shape(self, c4_lexer, src, expected):
        tokens = c4_lexer.tokenize(src)
        contents = _contents(tokens)
        assert contents == expected, f"{src!r} → {contents!r}"
