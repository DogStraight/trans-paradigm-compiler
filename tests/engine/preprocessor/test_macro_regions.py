"""宏区间表（`expand_tokens` 第三返回值）——外层处理宏的事实源。

每条区间同时给两个坐标：
- **源文本**坐标（`src_line`/`src_col`/`src_end_col`）：宏调用在源里的位置；
- **展开结果**字符区间（`offset`/`end_offset`）：宏体铺进文本后的位置。
消费方（渲染侧 raw 拼接 / 诊断宏归因）靠它定位"哪些内容来自哪条宏"。

Doc: preprocessor/_expand.py::expand_tokens
Doc: docs/decisions/0017-macro-in-syntax-position.md（决策 3）
"""

import pytest

from preprocessor._expand import expand_tokens, scan_directives

_RULES = "grammar/verilog"


def _expand(src: str) -> tuple[str, list[dict]]:
    """展开 → (展开文本, 区间表)。"""
    table, func_macros, _, _, _, clean, _ = scan_directives(src, _RULES)
    expanded, _, regions, _ = expand_tokens(
        clean,
        table,
        rules_dir=_RULES,
        func_macros=func_macros,
    )
    return expanded, regions


def _slice(expanded: str, region: dict) -> str:
    return expanded[region["offset"]:region["end_offset"]]


def test_single_line_macro() -> None:
    """单行宏：区间切出的就是宏体；源区间切出的就是宏调用原文。"""
    src = "`define V 1'b1\nmodule m;\n  assign a = `V;\nendmodule\n"
    expanded, regions = _expand(src)
    assert len(regions) == 1
    r = regions[0]
    assert r["name"] == "V" and r["is_func"] is False
    assert _slice(expanded, r) == "1'b1"
    # 源区间切出宏调用原文（clean 源坐标；本样本无指令行位移）
    clean_lines = "`define V 1'b1\nmodule m;\n  assign a = `V;\nendmodule\n".split("\n")
    assert clean_lines[r["src_line"] - 1][r["src_col"]:r["src_end_col"]] == "`V"


def test_multi_token_body_in_type_slot() -> None:
    """类型位宏（NT=wire）：区间切出宏体，展开文本即 `input wire d;`。"""
    src = "`define NT wire\nmodule m;\n  input `NT d;\nendmodule\n"
    expanded, regions = _expand(src)
    assert _slice(expanded, regions[0]) == "wire"
    assert "input wire d;" in expanded


def test_multi_line_body_spans_lines() -> None:
    """宏体含换行：区间跨行，切片内容仍等于宏体。

    契约用**字符偏移**而不是行/列：宏体含换行会让展开结果行数增加，行/列需要
    额外换算，偏移则天然稳定（消费方按 offset 定位 token/节点）。
    正常路径上 `` `define `` 的续行（行尾 `\\`）会在 `scan_directives` 里合并成
    单一逻辑行，故此处直接驱动函数、手造含换行的宏体。
    """
    src = "module m;\n  wire a;\n  assign a = `M;\nendmodule\n"
    body = "1'b1 +\n  1'b0"
    expanded, _, regions, line_map = expand_tokens(
        src, {"M": body}, rules_dir=_RULES
    )
    assert len(regions) == 1
    # 多行宏体：输出行数 > 源行数，映射里 3 行（源行 3）占 3 个输出行位
    assert line_map.count(3) == 1 + body.count("\n")
    r = regions[0]
    assert r["body"] == body
    assert _slice(expanded, r) == body
    # 宏体换行使展开结果比源多一行 → 偏移跨行仍可精确定位
    assert expanded.count("\n") == src.count("\n") + 1


def test_function_like_macro_records_call_and_substituted_body() -> None:
    """带参宏：source_text 是调用原文（含实参），body 是代入后的展开体。"""
    src = (
        "`define MIN(a, b) ((a) < (b) ? (a) : (b))\n"
        "module m;\n"
        "  assign z = `MIN(x, y);\n"
        "endmodule\n"
    )
    expanded, regions = _expand(src)
    assert len(regions) == 1
    r = regions[0]
    assert r["is_func"] is True
    assert r["source_text"] == "`MIN(x, y)"
    assert _slice(expanded, r) == "((x) < (y) ? (x) : (y))"


def test_two_macros_one_line_offsets_accumulate() -> None:
    """同一行两条宏：第二条的展开后偏移计入左侧替换的长度增量。"""
    src = (
        "`define A 1\n"
        "`define LONG_MACRO 2222\n"
        "module m;\n"
        "  assign z = {`A, `LONG_MACRO};\n"
        "endmodule\n"
    )
    expanded, regions = _expand(src)
    assert [r["name"] for r in regions] == ["A", "LONG_MACRO"]
    assert [_slice(expanded, r) for r in regions] == ["1", "2222"]
    # 区间按源顺序、且不重叠
    assert regions[0]["offset"] < regions[1]["offset"]


def test_body_trailing_comment_gets_newline() -> None:
    """宏体末行含行注释 → 拼接时末尾补换行（防吞同行后续内容）。

    不补的话 `` assign a = `V; `` 展开成 `assign a = 1'b1 // note;`——`;` 落进
    注释里，语句丢分号（darkriscv 实测 81 条误报的来源）。补换行后后续内容回到
    下一行，解析照常（Verilog 不看行）。
    """
    src = "`define V 1'b1 // note\nmodule m;\n  assign a = `V;\nendmodule\n"
    expanded, regions = _expand(src)
    assert len(regions) == 1
    r = regions[0]
    assert r["body"].endswith("\n"), r["body"]
    assert r["source_text"] == "`V"
    # 宏调用同行的 `;` 不在注释里（没被吞）
    assert ";" in expanded.split("// note")[1].split("\n")[1]


def test_inactive_branch_macro_not_recorded() -> None:
    """条件编译非活跃分支里的宏调用不进区间表（不展开不登记）。"""
    src = (
        "`define V 1'b1\n"
        "`ifdef NOPE\n"
        "`define V 1'b0\n"
        "`endif\n"
        "module m;\n"
        "  assign a = `V;\n"
        "endmodule\n"
    )
    expanded, regions = _expand(src)
    assert [r["name"] for r in regions] == ["V"]
    assert _slice(expanded, regions[0]) == "1'b1"


@pytest.mark.parametrize("body", ["wire", "reg [7:0]", "[7:0]"])
def test_body_slice_equals_region_content(body: str) -> None:
    """区间切片恒等于宏体（外层按区间取内容，不靠文本匹配猜）。"""
    src = f"`define M {body}\nmodule m;\n  input `M d;\nendmodule\n"
    expanded, regions = _expand(src)
    assert _slice(expanded, regions[0]) == body
