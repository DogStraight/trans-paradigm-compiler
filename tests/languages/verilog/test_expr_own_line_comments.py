"""表达式内独占行注释的落位（leading_own_line 槽 + 声明驱动硬换行）。

背景（2026-09-17 darkriscv 遗留 2 处）：语句**内部**的独占行注释
（`wire HLT =\n// c\n(expr)` 这类位置）以前只能靠"时域回插"的锚点插值
落位，而它的锚是清洁流里的下一个显著 token——折叠区里可以相距几十行，
插值必偏（条件块漂到语句之外或另一条语句上）。

现走**结构**通道：表达式入口/操作符间隙按三分类归位——
  - 行中（注释后同行有代码）→ inline_after（锚 token，行内插入）
  - 行尾（同行前有代码、注释后换行）→ leading（Text+Break，随操作数断行）
  - 独占行（注释前无同行代码）→ leading_own_line（硬换行独占成行）
「行终止型」由语言包声明驱动（renderer.comment_ends_line），引擎不硬编码
注释语法。

本文件测试覆盖：独占行条件块在语句内部落在源序位置（`=` 之后、右操作数
之前，且块独立成行）；行尾注释仍随操作数断行（不误升为独占行）。
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

from pipeline import run_pipeline_on_source  # noqa: E402


def _run(src: str, fmt: bool) -> str:
    r = run_pipeline_on_source(
        source=src, rules_dir="grammar/verilog", quiet=True,
        no_lint=True, format_output=fmt, expand_macros=True,
    )
    assert r["success"], r.get("error", "")
    return r.get("output", "")


# 语句内部的独占行条件块：`=` 后换行 → 条件块 → 右操作数（源序）
_WIRE_IFDEF_SRC = (
    "module m;\n"
    "    wire a = \n"
    "`ifdef X\n"
    "        b | c;\n"
    "`endif\n"
    "        d;\n"
    "endmodule\n"
)


def test_condition_block_inside_statement_keeps_position() -> None:
    """条件块落在 `=` 之后、右操作数之前，且自身独立成行。

    旧缺陷：marker 由锚点插值落回，块文本被并进 `wire a = ...` 同行
    （`wire a = `ifdef X`）——既不是源断行位置，也不是合法排版。
    """
    for fmt in (False, True):
        out = _run(_WIRE_IFDEF_SRC, fmt)
        assert out.count("<tpc:") == 0, out
        i_eq = out.index("wire a =")
        i_if = out.index("`ifdef X")
        i_else_body = out.index("b | c;")
        i_rhs = out.index("d;")
        assert i_eq < i_if < i_else_body < i_rhs, f"[fmt={fmt}] 条件块位置错:\n{out}"
        # 块首独立成行：`ifdef` 所在行的上一行以 `=` 收尾
        lines = out.splitlines()
        i_line = next(i for i, l in enumerate(lines) if l.strip() == "`ifdef X")
        assert lines[i_line - 1].rstrip().endswith("="), (
            f"[fmt={fmt}] 条件块未独立成行:\n{out}"
        )
        # `endif` 与右操作数分属两行
        tail = out[i_else_body:]
        assert tail.index("`endif") < tail.index("d;"), out


_TRAILING_COMMENT_SRC = (
    "module m;\n"
    "    wire a = b || // why\n"
    "        c;\n"
    "endmodule\n"
)


def test_trailing_comment_stays_with_operator_line() -> None:
    """行尾注释（`|| // why`）随操作符行、不误升为独占行。

    与独占行的区别只在"注释前同行有无代码"——判错会把行尾注释推到
    独立行，改变源里的片段归属。
    """
    for fmt in (False, True):
        out = _run(_TRAILING_COMMENT_SRC, fmt)
        line_with_op = next(l for l in out.splitlines() if "||" in l)
        assert "// why" in line_with_op, f"[fmt={fmt}] 行尾注释被移出行:\n{out}"
