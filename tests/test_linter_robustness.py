"""Linter 健壮性契约测试 — 对异常/边界输入不崩溃。

固定"输入无论如何都不抛异常（崩溃冒泡）"的契约：
    - 空/纯注释/畸形/垃圾/残缺输入 → 正常返回诊断或空
    - CRLF 行尾 / UTF-8 BOM 等 lexer 当前无法处理的输入 → 转 lexer-error
      诊断而非崩溃（通用防御，不硬编码具体格式；lexer 侧修复后这些输入
      自然正常解析，本测试仍绿——契约是"不崩溃"，不是"必然 lexer-error"）
    - 边界输入不应产生检查器内部错误（linter-internal-error，防假绿）

新增边界输入时，只需在参数列表加一行即可扩展。
"""

import pytest
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


@pytest.fixture(scope="module")
def scanner(config_loaded):
    from linter.scanner import LinterScanner

    return LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)


# 边界/畸形输入（不应崩溃冒泡）
_BOUNDARY_INPUTS = [
    "",  # 空
    "   \n\t\n  ",  # 纯空白
    "// just a comment\n/* block */\n",  # 纯注释
    "module",  # 残缺关键字
    "begin",
    "endmodule",
    "assign",
    ")))(((",  # 畸形括号
    "!!!@@@###",  # 垃圾字符
    "modu",  # 半个关键字
    "module m; always endmodule",  # 残缺语句
    ";;;",  # 只有分号
    'module m; wire "abc; endmodule',  # 未闭合字符串
    "12345",  # 数字开头
    "module ; endmodule",  # 模块缺名
]


class TestNoCrash:
    """任何输入都不应抛异常（崩溃冒泡）。"""

    @pytest.mark.parametrize("src", _BOUNDARY_INPUTS)
    def test_boundary_inputs_do_not_crash(self, scanner, src):
        # scan 正常返回（抛异常则 pytest 失败）
        scanner.scan(src)

    def test_crlf_input_does_not_crash(self, scanner):
        # CRLF 行尾（lexer 当前可能无法处理）→ 不崩溃，正常返回
        errs = scanner.scan("module m;\r\n    assign a = b;\r\nendmodule\r\n")
        assert isinstance(errs, list)

    def test_bom_input_does_not_crash(self, scanner):
        # UTF-8 BOM → 不崩溃，正常返回
        errs = scanner.scan("\ufeffmodule m;\n    assign a = b;\nendmodule\n")
        assert isinstance(errs, list)


class TestNoInternalError:
    """边界输入不应产生检查器内部错误（linter-internal-error 防假绿）。"""

    @pytest.mark.parametrize(
        "src",
        [
            "",
            "module",
            ")))(((",
            "module m; always endmodule",
            "module m; wire a endmodule",
            "module m;\n    assign a = b;\nendmodule\n",
        ],
    )
    def test_no_internal_error(self, scanner, src):
        errs = scanner.scan(src)
        assert not any(
            e.code == "linter-internal-error" for e in errs
        ), f"检查器内部错误: {[e.message for e in errs if e.code == 'linter-internal-error']}"
