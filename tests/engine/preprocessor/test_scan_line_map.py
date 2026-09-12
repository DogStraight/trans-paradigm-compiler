"""scan_directives 行映射（clean 行 → 原始源行）——诊断回源第二级表。

契约：`clean_to_raw[k-1]` = clean 第 k 行（1-based）的原始源行号（1-based）。
覆盖延续行合并（多→1，取段首行）、指令行占位（1:1）、条件块压缩
（多→1，含 inactive 分支丢弃）、include 拼接行（None 不可映射）。

Doc: preprocessor/_expand.py::scan_directives
Doc: docs/gaps/gap-macro-diagnostic-mapping.md
"""

from preprocessor._expand import scan_directives

_RULES = "grammar/verilog"


def _clean_and_map(src: str, **kw) -> tuple[str, list]:
    _, _, _, _, _, clean, clean_to_raw = scan_directives(src, _RULES, **kw)
    return clean, clean_to_raw


def test_no_directives_identity() -> None:
    src = "module m;\n  wire a;\nendmodule\n"
    clean, line_map = _clean_and_map(src)
    assert clean == src
    assert line_map == [1, 2, 3, 4]


def test_continuation_merge_takes_first_line() -> None:
    src = "assign x = \\\n  1'b1;\nwire y;\n"
    clean, line_map = _clean_and_map(src)
    assert clean.split("\n")[0] == "assign x = 1'b1;"
    # 合并段取首行（1）；后续行号顺延（3、4）
    assert line_map == [1, 3, 4]


def test_directive_marker_keeps_line_number() -> None:
    src = "`define A 1\nwire y;\n"
    clean, line_map = _clean_and_map(src)
    assert clean.split("\n")[0].startswith("// <tpc:directive:")
    assert line_map == [1, 2, 3]


def test_cond_block_compression_maps_active_lines() -> None:
    """ifdef 选中分支：active 内容保行号；压缩占位吞掉 skipped 行。"""
    src = (
        "`define F 1\n"      # 1
        "module m;\n"        # 2
        "`ifdef F\n"         # 3
        "  wire a;\n"        # 4
        "`else\n"            # 5
        "  wire b;\n"        # 6
        "  wire c;\n"        # 7
        "`endif\n"           # 8
        "  wire z;\n"        # 9
        "endmodule\n"        # 10
    )
    clean, line_map = _clean_and_map(src)
    assert "wire a;" in clean
    assert "wire b;" not in clean and "wire c;" not in clean  # inactive 不保留
    # clean：指令占位(1) module(2) 占位(3) wire a(4) 占位(5) wire z(9) endmodule(10) 尾行(11)
    assert line_map == [1, 2, 3, 4, 5, 9, 10, 11]


def test_cond_block_all_inactive_collapses_to_one_line() -> None:
    src = "wire p;\n`ifdef A\nwire q;\n`elsif B\nwire r;\n`endif\nwire s;\n"
    clean, line_map = _clean_and_map(src)
    assert "wire q;" not in clean and "wire r;" not in clean
    lines = clean.split("\n")
    assert len(lines) == 4  # p + 整块占位 + s + 尾行
    # 整块压 1 行：行号从 2 跳到 7
    assert line_map == [1, 2, 7, 8]


def test_include_spliced_lines_unmappable(tmp_path) -> None:
    (tmp_path / "inc.v").write_text("wire inc_a;\nwire inc_b;\n", encoding="utf-8")
    src = 'wire top;\n`include "inc.v"\nwire tail;\n'
    clean, line_map = _clean_and_map(
        src, source_path=str(tmp_path / "main.v"), search_dirs=[str(tmp_path)]
    )
    assert "wire inc_a;" in clean and "wire tail;" in clean
    # 拼接行（含被包含文件尾空行）不属于本源文件 → None；宿主行照常记账
    assert line_map == [1, None, None, None, 2, 3, 4]
