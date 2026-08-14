"""formatter 超宽行不变式测试（wrap 折行已移除）。

验证移除折行后：
  - 格式化幂等（二次 format 稳定）
  - 不改 token（去空白后一致）
  - 不误伤：短行/端口行/声明（无 =）——超宽行保持原样不折
"""

import pytest

from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR

pytestmark = pytest.mark.usefixtures("config_loaded")


def _fmt(src: str) -> str:
    return format_source(src, DEFAULT_RULES_DIR)


class TestWrap:
    def test_wrap_idempotent(self):
        """格式化幂等（二次 format 稳定）。"""
        src = (
            "module m;\n"
            "    wire mem_la_firstword_xfer = COMPRESSED_ISA && mem_xfer && "
            "( !last_mem_valid ? mem_la_firstword : mem_la_firstword_reg );\n"
            "endmodule\n"
        )
        a = _fmt(src)
        b = _fmt(a)
        assert a == b, "二次格式化漂移"

    def test_wrap_token_complete(self):
        """折行不改 token（去空白后一致）。"""
        src = (
            "module m;\n"
            "    assign x = a && b && c && d && e && f && g && h && i && j && k && l;\n"
            "endmodule\n"
        )
        out = _fmt(src)

        def strip_all(text: str) -> str:
            lines = []
            for line in text.splitlines():
                ci = line.find("//")
                if ci >= 0:
                    line = line[:ci]
                lines.append(line)
            return "".join("".join(lines).split())

        assert strip_all(out) == strip_all(src)

    def test_short_lines_untouched(self):
        """短行不折（原样保留）。"""
        src = "module m;\n    assign a = b;\nendmodule\n"
        out = _fmt(src)
        assert "    assign a = b;" in out.split("\n")

    def test_port_lines_not_wrapped(self):
        """端口行（input/output/inout）不折。"""
        long_port = "input  [31:0] mem_rdata_latched_noshuffle_and_more_signal_names_here,"
        src = f"module m (\n    {long_port}\n    input clk\n);\nendmodule\n"
        out = _fmt(src)
        assert long_port in out, "端口行不应折行"

    def test_decl_no_init_not_wrapped(self):
        """声明无 `=`（如 reg [31:0] x;）不折。"""
        long_decl = "reg [31:0] some_really_long_signal_name_that_exceeds_width_yes,"
        src = f"module m;\n    {long_decl}\nendmodule\n"
        out = _fmt(src)
        assert long_decl in out, "无 init 声明不应折行"
