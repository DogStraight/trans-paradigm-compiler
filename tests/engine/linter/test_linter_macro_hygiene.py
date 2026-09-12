"""linter 宏/指令卫生检查（MH 族）单元测试。

覆盖（对标精确判定，见 docs/references.md「宏/指令卫生族 + 排版族归属补充调研」）：

    - MH001 nettype 复位缺失：设 `` `default_nettype none `` 未复位 → 报；
      已复位 wire / 未使用该指令 → 不报（对齐 svlint default_nettype_wire_at_end）
    - MH002 宏重定义未 undef：异值重定义 → 报；**同值重定义 → 不报**
      （对齐 Verilator REDEFMACRO）；先 undef 再定义 → 不报；
      多行宏体（续行）值不确定 → 不误报（保守优先）
    - 配置驱动边界：语言包未声明指令关键字 → 对应子检查不启用
"""

from core.define import DEFAULT_RULES_DIR
from linter.checkers.macro_hygiene import MacroHygieneChecker
from linter.scanner import LinterScanner

import pytest


@pytest.fixture
def scanner():
    """verilog 语言包 linter 扫描器（配置含 [linter.macro_hygiene]）。"""
    return LinterScanner(rules_dir=DEFAULT_RULES_DIR)


def _codes(diags) -> list[str]:
    return [d.code for d in diags]


class TestNettypeRestore:
    """MH001 — nettype 指令未复位（文件末尾生效值非复位值）。"""

    def test_unrestored_reports(self, scanner):
        """设 `default_nettype none` 但未复位 → MH001，定位到最后一条指令行。"""
        src = "`default_nettype none\nmodule m;\nendmodule\n"
        diags = scanner.scan(src)
        assert "MH001" in _codes(diags)
        d = next(d for d in diags if d.code == "MH001")
        assert d.range[0].line == 0
        assert "none" in d.message

    def test_restored_ok(self, scanner):
        """末尾复位为 wire → 零 MH001。"""
        src = "`default_nettype none\nmodule m;\nendmodule\n`default_nettype wire\n"
        assert "MH001" not in _codes(scanner.scan(src))

    def test_last_effective_value_wins(self, scanner):
        """多条指令取"末尾生效值"：中间复位过但末尾又改回 none → 报。"""
        src = (
            "`default_nettype none\n"
            "`default_nettype wire\n"
            "`default_nettype none\n"
            "module m;\nendmodule\n"
        )
        diags = [d for d in scanner.scan(src) if d.code == "MH001"]
        assert len(diags) == 1
        assert diags[0].range[0].line == 2  # 最后一条指令行

    def test_never_used_ok(self, scanner):
        """未使用该指令 → 不报（"未复位"以"使用过"为前提）。"""
        src = "module m;\nendmodule\n"
        assert "MH001" not in _codes(scanner.scan(src))

    def test_indented_directive(self, scanner):
        """指令行带前导缩进仍生效（与 preprocessor 的行首判定同源）。"""
        src = "  `default_nettype none\nmodule m;\nendmodule\n"
        assert "MH001" in _codes(scanner.scan(src))


class TestMacroRedef:
    """MH002 — 宏重定义未先 undef（值不同才报）。"""

    def test_different_value_reports(self, scanner):
        """异值重定义 → MH002，消息含新旧值。"""
        src = "`define DUP def1\n`define DUP def2\nmodule m;\nendmodule\n"
        diags = [d for d in scanner.scan(src) if d.code == "MH002"]
        assert len(diags) == 1
        assert diags[0].range[0].line == 1  # 重定义那一行
        assert "def1" in diags[0].message and "def2" in diags[0].message

    def test_same_value_ok(self, scanner):
        """同值重定义 → 不报（对齐 Verilator REDEFMACRO 的"值不同"边界）。"""
        src = "`define DUP def1\n`define DUP def1\nmodule m;\nendmodule\n"
        assert "MH002" not in _codes(scanner.scan(src))

    def test_undef_then_redefine_ok(self, scanner):
        """先 undef 再重定义 → 不报（意图已表明）。"""
        src = "`define DUP a\n`undef DUP\n`define DUP b\nmodule m;\nendmodule\n"
        assert "MH002" not in _codes(scanner.scan(src))

    def test_multiline_body_conservative(self, scanner):
        """多行宏体（续行）值不确定 → 不误报（宁可漏报）。"""
        src = (
            "`define BODY a = 1;\n"
            "`define BODY \\\n"
            "    b = 2;\n"
            "module m;\nendmodule\n"
        )
        assert "MH002" not in _codes(scanner.scan(src))

    def test_no_body_redef(self, scanner):
        """无体定义（`` `define FLAG ``）与有体定义重定义 → 值不同即报。"""
        src = "`define FLAG 1\n`define FLAG\nmodule m;\nendmodule\n"
        assert "MH002" in _codes(scanner.scan(src))


class TestConfigDriven:
    """配置驱动边界：语言包未声明指令关键字 → 子检查不启用（零误报）。"""

    def test_empty_cfg_no_diag(self):
        """空配置（如 c4 未声明）→ 零诊断。"""
        src = "`default_nettype none\n`define A 1\n`define A 2\n"
        checker = MacroHygieneChecker(src, "`", {})
        assert checker.validate([]) == []

    def test_partial_cfg_only_declared_subcheck(self):
        """只声明宏指令关键字（无 nettype）→ 仅 MH002 生效。"""
        src = "`default_nettype none\n`define A 1\n`define A 2\n"
        cfg = {
            "define_directive": "define",
            "undef_directive": "undef",
        }
        codes = _codes(MacroHygieneChecker(src, "`", cfg).validate([]))
        assert codes == ["MH002"]

    def test_no_token_dependency(self):
        """文件级检查：不消费 token 区间（传空 token 列表仍工作）。"""
        src = "`default_nettype none\nmodule m;\nendmodule\n"
        cfg = {"nettype_directive": "default_nettype", "nettype_restore": "wire"}
        codes = _codes(MacroHygieneChecker(src, "`", cfg).validate([]))
        assert codes == ["MH001"]
