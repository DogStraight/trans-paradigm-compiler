"""formatter ifdef 注释标注回归测试（VeriGood 借鉴）。

验证 `` `else `` / `` `endif `` 补配对宏名注释：
  - 基本配对（ifdef/else/endif → else // NAME / endif // NAME）
  - elsif 保留自身条件名（`elsif FEATURE_B // FEATURE_B）
  - 幂等（已有注释不重复、二次标注稳定）
  - 孤指令（空栈）不补
"""

import pytest

from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR
from grammar.verilog.plugins.formatter.passes.ifdef_annotate import run_ifdef_annotate

pytestmark = pytest.mark.usefixtures("config_loaded")


class TestIfdefAnnotate:
    def test_basic_pair(self):
        """ifdef/else/endif 配对补注释。"""
        lines = [
            "`ifdef FEATURE_A",
            "    wire a;",
            "`else",
            "    wire b;",
            "`endif",
        ]
        out = run_ifdef_annotate(lines)
        assert "`else // FEATURE_A" in out
        assert "`endif // FEATURE_A" in out

    def test_elsif_preserves_own_condition(self):
        """elsif 保留自身条件名。"""
        lines = ["`ifdef A", "`elsif B", "`endif"]
        out = run_ifdef_annotate(lines)
        assert "`elsif B // B" in out
        assert "`endif // A" in out

    def test_idempotent(self):
        """已有注释不重复；二次标注稳定。"""
        lines = [
            "`ifdef X",
            "`else // already",
            "`endif // already",
        ]
        out = run_ifdef_annotate(lines)
        assert "`else // already" in out  # 不覆盖已有注释
        assert "\n".join(out).count("// already") == 2  # else + endif 各一
        # 幂等
        assert run_ifdef_annotate(out) == out

    def test_orphan_directive_no_annotate(self):
        """孤 `else/`endif（空栈）不补。"""
        lines = ["`else", "`endif"]
        out = run_ifdef_annotate(lines)
        assert out == lines  # 无配对宏名，原样保留

    def test_integration_format_source(self):
        """format_source 管线内生效且幂等。"""
        src = (
            "`ifdef FEATURE\n"
            "module m;\n"
            "    wire a;\n"
            "endmodule\n"
            "`else\n"
            "module m;\n"
            "    wire b;\n"
            "endmodule\n"
            "`endif\n"
        )
        a = format_source(src, DEFAULT_RULES_DIR)
        b = format_source(a, DEFAULT_RULES_DIR)
        assert a == b, "ifdef 标注二次格式化漂移"
        assert "`else // FEATURE" in a
        assert "`endif // FEATURE" in a
