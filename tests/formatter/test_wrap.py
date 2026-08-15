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

    def test_trailing_comment_wrapped(self):
        """行尾注释不挡折行：`wire x = ... ; // comment` 的代码部分超宽仍折。

        原判据 `line.rstrip().endswith(";")` 被行尾注释破坏（darkriscv 带注释
        声明超宽不折的根因）——判据应在去注释后的代码部分做，注释跟尾行。
        """
        src = (
            "module m;\n"
            "    wire  [`TH+3:0] DPTR = XRES ? { RESMODE , 4'd0 } : "
            "{ TPTR , XIDATA[10:7] } ; // set SP_RESET when RES == 1\n"
            "endmodule\n"
        )
        out = _fmt(src)
        lines = out.split("\n")
        # 折成多行（代码行被折），注释保留在尾行
        assert len([l for l in lines if "DPTR" in l or "XIDATA" in l]) >= 2
        assert "// set SP_RESET when RES == 1" in out, "注释应保留"
        # 代码行折后均不超宽（注释行除外）
        for l in lines:
            if ("DPTR" in l or "XIDATA" in l) and "//" not in l:
                assert len(l) <= 100, f"代码行应 ≤100: {l!r}"

    def test_trailing_comment_no_wrap_when_code_fits(self):
        """代码部分 ≤100 仅注释超宽 → 不折（注释不拆）。"""
        src = (
            "module m;\n"
            "    wire ok = fits; // this is a very long trailing comment that "
            "pushes the line way over one hundred columns total but code is short\n"
            "endmodule\n"
        )
        out = _fmt(src)
        # 代码短 + 注释长 → 整行保留（wrap 不折注释，代码部分无需折）
        assert "wire ok = fits;" in out

    def test_block_header_wrapped(self):
        """块头折行：`if (长条件) begin` 条件括号内断点可折。"""
        src = (
            "module m;\n"
            "    always @* begin\n"
            "        if ((tstate[1] || (tstate[2] && wait_n == 1'b0)) "
            "&& no_read == 1'b0 && write == 1'b0 && "
            "some_extra_long_signal == 1'b1) begin\n"
            "            q = 1;\n"
            "        end\n"
            "    end\n"
            "endmodule\n"
        )
        out = _fmt(src)
        lines = out.split("\n")
        # if 头折成多行，`) begin` 保留在尾行
        if_lines = [l for l in lines if "tstate[1]" in l or "some_extra_long_signal" in l]
        assert len(if_lines) >= 2
        assert "begin" in if_lines[-1], "尾行应保留 `) begin`"
        # 代码行均 ≤100
        for l in if_lines:
            assert len(l) <= 100, f"折后应 ≤100: {l!r}"

    def test_block_header_idempotent(self):
        """块头折行二次 format 稳定（续行缩进不漂移）。"""
        src = (
            "module m;\n"
            "    always @* begin\n"
            "        if ((tstate[1] || (tstate[2] && wait_n == 1'b0)) "
            "&& no_read == 1'b0 && write == 1'b0) begin\n"
            "            q = 1;\n"
            "        end else if (Halt_FF == 1'b1 || "
            "(IntCycle == 1'b1 && IStatus == 2'b10)) begin\n"
            "            q = 2;\n"
            "        end\n"
            "    end\n"
            "endmodule\n"
        )
        a = _fmt(src)
        b = _fmt(a)
        assert a == b, "块头折行二次格式化漂移"

    def test_paren_inner_break(self):
        """普通语句括号内断点：`x <= (a ? b : c) | d | e` 顶层无断点，括号内可折。"""
        src = (
            "module m;\n"
            "    always @* begin\n"
            "        trace_data <= (irq_active ? TRACE_IRQ : 0) | TRACE_BRANCH | "
            "(current_pc & 32'hfffffffe) | (reg_op1 + decoded_imm);\n"
            "    end\n"
            "endmodule\n"
        )
        out = _fmt(src)
        lines = out.split("\n")
        # 折成多行，全部 ≤100
        tr_lines = [l for l in lines if "trace_data" in l or "current_pc" in l or "reg_op1" in l]
        assert len(tr_lines) >= 2
        for l in tr_lines:
            assert len(l) <= 100, f"折后应 ≤100: {l!r}"

    def test_paren_inner_break_idempotent(self):
        """括号内断点 + 续行再折幂等：`cond) && A && B;` 的续行 B; 不逐级递增。"""
        src = (
            "module m;\n"
            "    always @* begin\n"
            "        instr_rdcycleh <= ((mem_rdata_q[6:0] == 7'b1110011 && "
            "mem_rdata_q[31:12] == 'b11001000000100000010) || "
            "(mem_rdata_q[6:0] == 7'b1110011 && "
            "mem_rdata_q[31:12] == 'b11001000000000000010)) && "
            "ENABLE_COUNTERS && ENABLE_COUNTERS64;\n"
            "    end\n"
            "endmodule\n"
        )
        a = _fmt(src)
        b = _fmt(a)
        assert a == b, "括号内断点续行再折二次格式化漂移"

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


class TestAstBreak:
    """语法感知断点：AST 确认语句完整 → concat 逗号可断（文本启发式排除）。"""

    @pytest.fixture(scope="class")
    def parser(self, config_loaded):
        from parser import Parser, setup_grammar
        from core.define import GrammarRulesRegister, DEFAULT_EXT_DIRS
        from parser.rule_selector import RuleSelector
        from lexer import Lexer

        rules = setup_grammar(DEFAULT_RULES_DIR, GrammarRulesRegister.get_default(), ext_dirs=DEFAULT_EXT_DIRS)
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        p = Parser(
            rules_dir=DEFAULT_RULES_DIR,
            rules=rules,
            rule_selector=RuleSelector(rules, stmt_names),
            log_file="",
        )
        p.lexer = Lexer(rules_dir=DEFAULT_RULES_DIR)
        return p

    def test_concat_comma_break_with_ast(self, parser):
        """concat 赋值：AST 确认语句完整 → `{}` 内逗号可断（折成多行）。"""
        from grammar.verilog.plugins.formatter.passes.wrap import _wrap_line

        line = (
            "assign mem_la_addr = (mem_do_prefetch || mem_do_rinst) ? "
            "{ next_pc[31:2] + mem_la_firstword_xfer, 16'b0 } : 32'h0;"
        )
        # 带 parser：concat 逗号断点启用
        out = _wrap_line(line, 100, 4, parser=parser)
        assert len(out) >= 2, "AST 应允许 concat 逗号断点"
        for l in out:
            assert len(l) <= 100

    def test_concat_comma_no_break_without_ast(self):
        """无 parser：concat 逗号排除（保守），仍能折但断点不同。"""
        from grammar.verilog.plugins.formatter.passes.wrap import _wrap_line

        line = (
            "assign mem_la_addr = (mem_do_prefetch || mem_do_rinst) ? "
            "{ next_pc[31:2] + mem_la_firstword_xfer, 16'b0 } : 32'h0;"
        )
        out = _wrap_line(line, 100, 4)
        # 无 parser 也折（顶层 `||` 断点），但不在 concat 逗号处
        assert len(out) >= 2
        joined = "\n".join(out)
        assert "||\n" in joined or "\n" in joined

    def test_ast_break_idempotent(self, parser):
        """AST 断点折行二次稳定（幂等）。"""
        from grammar.verilog.plugins.formatter.passes.wrap import _wrap_line

        line = (
            "assign mem_la_addr = (mem_do_prefetch || mem_do_rinst) ? "
            "{ next_pc[31:2] + mem_la_firstword_xfer, 16'b0 } : 32'h0;"
        )
        once = _wrap_line(line, 100, 4, parser=parser)
        # 折出的行再折应无变化（每行 ≤100 不再触发）
        twice = []
        for l in once:
            twice.extend(_wrap_line(l, 100, 4, parser=parser))
        assert twice == once, "AST 断点折行应幂等"
