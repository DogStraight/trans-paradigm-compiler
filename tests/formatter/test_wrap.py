"""wrap.py 宽度折行 pass 测试。

验证：
  - 超宽行在安全断点拆行（幂等、不改 token）
  - 续行缩进 = 语句头 +1
  - 不误伤：端口行/短行/注释/指令/声明（无 =）
"""

import pytest

from grammar.verilog.plugins.formatter import format_source
from core.define import DEFAULT_RULES_DIR

pytestmark = pytest.mark.usefixtures("config_loaded")


def _fmt(src: str) -> str:
    return format_source(src, DEFAULT_RULES_DIR)


def _find(out: list[str], key: str) -> str:
    for line in out:
        if key in line:
            return line
    raise AssertionError(f"未找到含 {key!r} 的行")


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


class TestWrap:
    def test_long_assign_wrapped(self):
        """超长 assign 在运算符断点折行，续行缩进 +1。

        顶层断点充足时拆到 ≤100；嵌套表达式（括号内断点不足）折在最近顶层
        断点——断言续行缩进正确 + 幂等（保守策略，不追求全 ≤100）。
        """
        src = (
            "module m;\n"
            "    assign mem_la_read = resetn && ( !mem_la_use_prefetched_high_word && "
            "!mem_state && ( mem_do_rinst || mem_do_prefetch || mem_do_rdata ) ) || "
            "( COMPRESSED_ISA && mem_xfer && !mem_la_secondword );\n"
            "endmodule\n"
        )
        out = _fmt(src).split("\n")
        # 首行保留 assign 头，续行缩进更深（+1 级）
        first = _find(out, "assign mem_la_read")
        assert _indent_of(first) == 4
        cont = [l for l in out if l.lstrip().startswith(("&&", "||"))]
        assert cont, "应有运算符续行"
        assert all(_indent_of(l) == 8 for l in cont), f"续行缩进应 8: {cont}"
        # 幂等
        assert _fmt("\n".join(out)) == "\n".join(out), "折行后二次格式化漂移"

    def test_wrap_idempotent(self):
        """折行幂等（二次 format 稳定）。"""
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

    def test_simple_long_fully_wrapped(self):
        """顶层断点充足：全折到 ≤100。"""
        src = (
            "module m;\n"
            "    assign x = a1 && b2 && c3 && d4 && e5 && f6 && g7 && h8 && "
            "i9 && j10 && k11 && l12 && m13 && n14;\n"
            "endmodule\n"
        )
        out = _fmt(src).split("\n")
        assert all(len(l) <= 100 for l in out), f"仍有超宽行: {[l for l in out if len(l)>100]}"

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
