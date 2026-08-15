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

    def test_penalty_prefers_balanced_break(self):
        """惩罚搜索：放弃会让首行超列的最右断点，选两行都不超的方案。

        Verible 惩罚模型：断点惩罚 + 超列惩罚（over_column_penalty）。
        最右断点（pos=107）会让首行超 7 列（70 惩罚），惩罚模型选 92
        （两行都不超，仅断点惩罚 10）。
        """
        src = (
            "module m;\n"
            "    wire very_long_signal_name = condition_a && condition_b && "
            "condition_c && condition_d && condition_e && condition_f;\n"
            "endmodule\n"
        )
        out = _fmt(src)
        lines = out.split("\n")
        # 折成两行：首行 ≤100（不是最右断点），尾行从操作数开始
        assert len([l for l in lines if "condition_" in l]) == 2
        assert all(len(l) <= 100 for l in lines if "condition_" in l)

    def test_penalty_idempotent_after_break(self):
        """惩罚折行后幂等（二次 format 不再漂移）。"""
        src = (
            "module m;\n"
            "    wire very_long_signal_name = condition_a && condition_b && "
            "condition_c && condition_d && condition_e && condition_f;\n"
            "endmodule\n"
        )
        a = _fmt(src)
        b = _fmt(a)
        assert a == b, "惩罚折行后二次格式化漂移"
