"""宏/条件编译文件的诊断行号回源（TODO ② (a)）。

两级复合链：scan_directives（原始→clean，条件压缩删行）→ expand_tokens
（clean→展开后，多行宏体拉长）→ FileResult.line_map → 两处诊断换算；
不可映射时保守回退展开行号（不给错误的源行号）。

Doc: analyzer/structure.py::_expand_source
Doc: analyzer/checker.py::_map_diag_line
Doc: docs/gaps/gap-macro-diagnostic-mapping.md
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from analyzer.checker import ProjectChecker


@pytest.fixture(scope="module")
def checker():
    return ProjectChecker(rules_dir="grammar/verilog")


def _un001_lines(report) -> list[int]:
    """语义诊断 UN001 的 1-based 行号（range 为 0-based LSP 坐标）。"""
    return [
        d["range"]["start"]["line"] + 1
        for f in report["files"]
        for d in f["semantic"]
        if d.get("code") == "UN001" and d.get("range")
    ]


def test_cond_compression_maps_later_lines(checker, tmp_path):
    """`ifdef 压缩删行后：块后诊断回源到原始行（此前是压缩后行号 6）。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "`define F 1\n"           # 1
        "module m;\n"             # 2
        "`ifdef F\n"              # 3
        "  wire a;\n"             # 4
        "`else\n"                 # 5
        "  wire b;\n"             # 6
        "  wire c;\n"             # 7
        "`endif\n"                # 8
        "  wire z_unused;\n"      # 9 ← UN001
        "  assign a = 1'b1;\n"    # 10
        "endmodule\n",            # 11
        encoding="utf-8",
    )
    report = checker.check(str(src))
    lines = _un001_lines(report)
    assert 9 in lines  # 源行 9（映射前为压缩后行号 6）


def test_multiline_macro_body_shifts_subsequent_lines(checker, tmp_path):
    """多行宏体（体末含行注释补换行）：宏后诊断回源到原始行。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "`define V 1'b1 // note\n"                       # 1
        "module m(input wire clk, output reg q);\n"      # 2
        "  always @(posedge clk) q <= `V;\n"             # 3 ← 展开后占 2 行
        "  wire z_unused;\n"                             # 4 ← UN001
        "endmodule\n",                                   # 5
        encoding="utf-8",
    )
    report = checker.check(str(src))
    lines = _un001_lines(report)
    assert 4 in lines  # 源行 4（映射前为展开行号 5）


def test_plain_file_lines_unchanged(checker, tmp_path):
    """无宏无指令：行号原样（映射恒等链，不产生偏移）。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "module m;\n"             # 1
        "  wire z_unused;\n"      # 2 ← UN001
        "endmodule\n",            # 3
        encoding="utf-8",
    )
    report = checker.check(str(src))
    assert 2 in _un001_lines(report)


def test_line_map_table_contract(checker, tmp_path):
    """表契约：展开行（0-based 索引）→ 原始源行（1-based）。"""
    src = tmp_path / "t.sv"
    src.write_text(
        "`define F 1\n"
        "module m;\n"
        "`ifdef F\n"
        "  wire a;\n"
        "`else\n"
        "  wire b;\n"
        "  wire c;\n"
        "`endif\n"
        "  wire z_unused;\n"
        "  assign a = 1'b1;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    checker.check(str(src))
    fr = checker._memo[str(src)]
    assert fr.line_map[5] == 9  # wire z_unused：展开行 5 → 原始行 9
    assert fr.line_map[1] == 2  # 块前段照常 1:1（module 行）
