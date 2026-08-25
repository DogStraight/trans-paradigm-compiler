"""保真度分级测试（ADR-0006 阶段 5）：keep_blank 空行回插。

keep_blank：渲染重排内容，但按源结构位置回插空行（LCS 匹配映射）。
验证：
  - 源相邻结构间的空行在输出对应位置保留
  - 不叠加 renderer 自身产生的空行
  - 无空行的源 → 输出不变
"""

import pytest

from renderer.fidelity import keep_blank_lines


class TestKeepBlank:
    def test_blank_between_structures(self):
        """源中相邻结构间的空行 → 输出对应位置保留。"""
        src = "module m;\n    wire a;\n\n    assign x = a;\nendmodule\n"
        out = "module m;\n    wire a;\n    assign x = a;\nendmodule\n"
        result = keep_blank_lines(src, out)
        lines = result.split("\n")
        # assign 前应有空行
        assert lines[2] == ""
        assert lines[3].strip().startswith("assign")

    def test_no_extra_blanks(self):
        """不叠加 renderer 自身空行（重排区不保留 out 空行）。"""
        src = "module m;\n    wire a;\n    wire b;\nendmodule\n"
        # out 自带空行（renderer 产生），src 无空行 → 应移除
        out = "module m;\n    wire a;\n\n    wire b;\nendmodule\n"
        result = keep_blank_lines(src, out)
        lines = result.split("\n")
        assert lines[1].strip() == "wire a;"
        assert lines[2].strip() == "wire b;"  # 无空行
        assert "" not in [l for l in lines if lines.index(l) not in (0, 3)]

    def test_no_blanks_source_strips_renderer_blanks(self):
        """src 无空行 → 输出中 renderer 自产空行被移除（空行以 src 为准）。"""
        src = "module m;\n    wire a;\n    wire b;\nendmodule\n"
        # out 自带 renderer 空行（module 头后、文件尾），src 无空行 → 移除
        out = "module m();\n\n    wire a;\n    wire b;\nendmodule\n\n"
        result = keep_blank_lines(src, out)
        lines = result.split("\n")
        # module 头后无空行（src 没有）
        assert lines[0].strip() == "module m();"
        assert lines[1].strip() == "wire a;"
        # wire a / wire b 之间无空行
        assert lines[2].strip() == "wire b;"

    def test_multiple_blank_lines(self):
        """源连续多个空行 → 保留数量。"""
        src = "module m;\n    wire a;\n\n\n    wire b;\nendmodule\n"
        out = "module m;\n    wire a;\n    wire b;\nendmodule\n"
        result = keep_blank_lines(src, out)
        lines = result.split("\n")
        assert lines[2] == "" and lines[3] == ""
        assert lines[4].strip() == "wire b;"

    def test_structural_reorder_keeps_blanks(self):
        """重排区（端口列表压行）后，结构空行仍按匹配位置回插。"""
        src = (
            "module top #(\n    parameter W = 8\n) (\n    input clk,\n"
            "    output [W-1:0] d\n);\n\n    wire a;\n\n    assign x = a;\nendmodule\n"
        )
        out = (
            "module top #( parameter W = 8 )(\n    input clk,\n"
            "    output [W-1:0] d);\n    wire a;\n    assign x = a;\nendmodule\n"
        )
        result = keep_blank_lines(src, out)
        lines = result.split("\n")
        # wire a 前保留空行
        assert "" in lines
        wi = next(i for i, l in enumerate(lines) if l.strip().startswith("wire a"))
        assert lines[wi - 1] == ""
        # assign 前保留空行
        ai = next(i for i, l in enumerate(lines) if l.strip().startswith("assign"))
        assert lines[ai - 1] == ""

    def test_empty_out(self):
        assert keep_blank_lines("module m;\n\nendmodule\n", "") == ""


class TestPipelineFidelity:
    def test_pipeline_keep_blank_param(self):
        """管线 fidelity 参数透传：keep_blank 按 src 结构回插空行。"""
        from pipeline import run_pipeline_on_source

        # src：module 头后无空行，wire a 与 assign 之间有空行
        src = "module m;\n    wire a;\n\n    assign x = a;\nendmodule\n"
        r_blank = run_pipeline_on_source(
            src, rules_dir="grammar/verilog",
            expand_macros=False, format_output=False, quiet=True,
            fidelity="keep_blank",
        )
        assert r_blank["success"]
        out = r_blank.get("output", "")
        lines = out.split("\n")
        # assign 前有空行（src 的空行被保留）
        ai = next(i for i, l in enumerate(lines) if l.strip().startswith("assign"))
        assert lines[ai - 1] == ""

    def test_pipeline_full_default(self):
        """默认 fidelity=full：行为与未传参数一致（零变化）。"""
        from pipeline import run_pipeline_on_source

        src = "module m;\n    wire a;\n\n    assign x = a;\nendmodule\n"
        r1 = run_pipeline_on_source(
            src, rules_dir="grammar/verilog",
            expand_macros=False, format_output=False, quiet=True,
        )
        r2 = run_pipeline_on_source(
            src, rules_dir="grammar/verilog",
            expand_macros=False, format_output=False, quiet=True,
            fidelity="full",
        )
        assert r1.get("output") == r2.get("output")
