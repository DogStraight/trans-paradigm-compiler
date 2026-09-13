"""linter 排版卫生检查（ST 族）单元测试。

覆盖（归属依据见 docs/references.md「宏/指令卫生族 + 排版族归属补充调研」）：

    - ST001 尾随空白：行尾空格/制表符 → 报；CRLF 的 \\r 不计；干净行不报
    - ST002 制表符：行内非尾随区 tab → 报（取首个位置，多处带计数）；
      尾随 tab 只报 ST001（无重叠）
    - ST003 行长超限：超上限 → 报（定位超出段）；= 上限不报；0 = 不检
    - 配置驱动：字段缺省（未声明语言包语义）→ 全不检查
"""

import pytest

from core.define import DEFAULT_RULES_DIR
from linter.checkers.style import StyleChecker
from linter.scanner import LinterScanner


@pytest.fixture
def scanner():
    """verilog 语言包 linter 扫描器（配置含 [linter.style_check]）。"""
    return LinterScanner(rules_dir=DEFAULT_RULES_DIR)


def _codes(diags) -> list[str]:
    return [d.code for d in diags]


class TestTrailingWhitespace:
    """ST001 — 尾随空白。"""

    def test_trailing_spaces_reported(self, scanner):
        src = "module m;\nendmodule  \n"
        diags = [d for d in scanner.scan(src) if d.code == "ST001"]
        assert len(diags) == 1
        assert diags[0].range[0].line == 1
        assert diags[0].range[0].character == 9  # "endmodule" 之后

    def test_trailing_tab_counted_as_trailing(self, scanner):
        """尾随制表符归 ST001（行尾空白），不双报 ST002。"""
        src = "module m;\t\nendmodule\n"
        codes = _codes(scanner.scan(src))
        assert "ST001" in codes
        assert "ST002" not in codes

    def test_crlf_carriage_return_not_flagged(self, scanner):
        """CRLF 行尾的 \\r 不算尾随空白。"""
        src = "module m;\r\nendmodule\r\n"
        assert "ST001" not in _codes(scanner.scan(src))

    def test_clean_line_ok(self, scanner):
        src = "module m;\nendmodule\n"
        assert "ST001" not in _codes(scanner.scan(src))

    def test_diag_is_warning_and_non_blocking(self, scanner):
        """severity=2（风格提示）+ blocking=False（不阻断语义/不计退出）。"""
        diags = [d for d in scanner.scan("module m;\nendmodule  \n") if d.code == "ST001"]
        assert diags[0].severity == 2
        assert diags[0].blocking is False


class TestTabCharacter:
    """ST002 — 行内制表符。"""

    def test_inner_tab_reported_at_first_position(self, scanner):
        src = "module m;\n\twire a;\nendmodule\n"
        diags = [d for d in scanner.scan(src) if d.code == "ST002"]
        assert len(diags) == 1
        assert diags[0].range[0].line == 1
        assert diags[0].range[0].character == 0

    def test_multiple_tabs_single_diag_with_count(self, scanner):
        """一行多处 tab → 单条诊断（首个位置 + 计数），不刷屏。"""
        src = "module m;\n\twire\ta;\nendmodule\n"
        diags = [d for d in scanner.scan(src) if d.code == "ST002"]
        assert len(diags) == 1
        assert "2 处" in diags[0].message


class TestLineWidth:
    """ST003 — 行长超限。"""

    def test_over_limit_reported(self, scanner):
        line = "  " + "a" * 99  # 101 字符
        src = f"module m;\n{line}\nendmodule\n"
        diags = [d for d in scanner.scan(src) if d.code == "ST003"]
        assert len(diags) == 1
        assert diags[0].range[0].line == 1
        assert diags[0].range[0].character == 100  # 超出段起点（上限列）

    def test_exactly_at_limit_ok(self, scanner):
        line = "  " + "a" * 98  # 恰好 100 字符
        src = f"module m;\n{line}\nendmodule\n"
        assert "ST003" not in _codes(scanner.scan(src))


class TestConfigDriven:
    """配置驱动边界。"""

    def test_undeclared_fields_disable_checks(self):
        """字段缺省（未声明语言包语义）→ 全不检查。"""
        src = "x \t\n" + "y" * 200 + "\n"
        assert StyleChecker(src, {}).validate([]) == []

    def test_limit_zero_disables_width(self):
        """max_line_width=0 → 只关行长，其余子检查不受影响。"""
        cfg = {
            "max_line_width": 0,
            "trailing_whitespace": True,
            "tab_character": True,
        }
        diags = StyleChecker("z" * 200 + "\n", cfg).validate([])
        assert diags == []
        diags = StyleChecker("z \n", cfg).validate([])
        assert _codes(diags) == ["ST001"]
