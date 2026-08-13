"""Linter 非法 token 检查（P0）单元测试 — MacroTokenChecker。

覆盖"未定义宏调用"检测（MacroTokenChecker 检查 macro.* token）：
    - 行内未定义宏（assign a = `FOO;）→ undefined-macro
    - 行内已定义宏（`define W 8 + `W'b0）→ 零误报
    - 多个未定义宏 → 各报一条
    - 未定义宏在范围表达式（[`BAD-1:0]）→ undefined-macro

已知边界（preprocessor 前置行为，非 linter 单责，不在本测试内处理）：
    - 行首以 ` 开头的"未知指令"行（如 `FOO a;）会被 preprocessor
      scan_directives 当指令行整体删除，MacroTokenChecker 收不到该行
      token → 不报。本测试聚焦 P0 可达场景（行内宏调用）。
"""

import pytest
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


@pytest.fixture(scope="module")
def p0_scanner(config_loaded):
    """已配置的 LinterScanner 实例（只开 P0 非法 token 检查）。"""
    from linter.scanner import LinterScanner

    ls = LinterScanner(
        DEFAULT_RULES_DIR,
        ext_dirs=DEFAULT_EXT_DIRS,
    )
    ls.enable_phase0 = True
    ls.enable_phase1 = False
    ls.enable_phase2 = False
    return ls


class TestUndefinedMacro:
    """行内未定义宏调用应报 undefined-macro。"""

    def test_inline_undefined_macro(self, p0_scanner):
        src = "module m;\n    assign a = `UNDEFINED;\nendmodule\n"
        errs = p0_scanner.scan(src)
        codes = [e.code for e in errs]
        assert "undefined-macro" in codes
        assert any("`UNDEFINED" in e.message for e in errs)

    def test_undefined_macro_in_range(self, p0_scanner):
        src = "module m;\n    reg [`BAD-1:0] data;\nendmodule\n"
        errs = p0_scanner.scan(src)
        assert any(e.code == "undefined-macro" for e in errs)

    def test_multiple_undefined_macros(self, p0_scanner):
        src = "module m;\n    assign a = `FOO;\n    assign b = `BAR;\nendmodule\n"
        errs = p0_scanner.scan(src)
        macros = [e.message for e in errs if e.code == "undefined-macro"]
        assert len(macros) == 2


class TestDefinedMacro:
    """已定义宏调用不应报 undefined-macro。"""

    def test_inline_defined_macro_no_error(self, p0_scanner):
        src = "module m;\n`define W 8\n    assign a = `W'b0;\nendmodule\n"
        assert p0_scanner.scan(src) == []

    def test_no_macro_no_error(self, p0_scanner):
        src = "module m;\n    assign a = 1;\nendmodule\n"
        assert p0_scanner.scan(src) == []
