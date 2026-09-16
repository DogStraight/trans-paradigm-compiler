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


def _norm(out: str) -> str:
    """空白归一化副本——formatter 会做列对齐（`wire   a =`），顺序断言用。"""
    return " ".join(out.split())


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
        flat = _norm(out)
        i_eq = flat.index("wire a =")
        i_if = flat.index("`ifdef X")
        i_else_body = flat.index("b | c;")
        i_rhs = flat.index("d;")
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


# 同因缺陷的最重形态：块漂到**相邻的**下一条语句（darkriscv `wire BMUX =`）
_NEIGHBOUR_STMT_SRC = (
    "module m;\n"
    "    wire a = \n"
    "`ifdef X\n"
    "        b;\n"
    "`endif\n"
    "        c;\n"
    "    wire z = y && w;\n"
    "endmodule\n"
)


def test_statement_interior_block_does_not_drift_to_next_stmt() -> None:
    """语句内部条件块不得漂到相邻语句（旧缺陷：锚点插值落到了下一条语句）。

    darkriscv 实测：`RMDATA` 的 `__MEXT__` 块被插值抬到 `wire BMUX =` 之后。
    现由结构定位（挂在右操作数节点的 leading_own_line），块只会在本语句内。
    """
    for fmt in (False, True):
        out = _run(_NEIGHBOUR_STMT_SRC, fmt)
        assert out.count("`ifdef X") == 1, f"[fmt={fmt}] 条件块丢失/重复:\n{out}"
        flat = _norm(out)
        i_a = flat.index("wire a =")
        i_if = flat.index("`ifdef X")
        i_z = flat.index("wire z =")
        assert i_a < i_if < i_z, f"[fmt={fmt}] 条件块漂到相邻语句:\n{out}"


# 右操作数是宏调用（渲染端"直出文本"节点）：附着注释不得随节点静默丢失
_MACRO_RHS_SRC = (
    "`define M(x) ((x)+1)\n"
    "module m;\n"
    "    wire a =\n"
    "`ifdef X\n"
    "        b;\n"
    "`endif\n"
    "        `M(c);\n"
    "endmodule\n"
)


def test_interior_block_survives_verbatim_rhs() -> None:
    """宏调用作右操作数时，语句内部条件块必须保留（不得整块消失）。

    直出文本节点（`_verbatim_text`）不走布局：若前置槽不输出，marker 不会
    进入渲染文本 → preprocessor 侧的条件块原文就永远没有回插时机（实测丢块）。
    """
    for fmt in (False, True):
        out = _run(_MACRO_RHS_SRC, fmt)
        assert out.count("`ifdef X") == 1, f"[fmt={fmt}] 条件块丢失/重复:\n{out}"
        assert "`M(c)" in out or "M (c)" in out, f"[fmt={fmt}] 宏调用丢失:\n{out}"
        flat = _norm(out)
        assert flat.index("wire a =") < flat.index("`ifdef X"), f"[fmt={fmt}] 顺序错:\n{out}"


# 注释落在 `inline = true` 规则（Init）上的两种形态：行中 / 行尾
_INLINE_RULE_MIDLINE_SRC = "module m;\n    wire a = /* c */ b;\nendmodule\n"
_INLINE_RULE_EOL_SRC = "module m;\n    wire a = // why\n        b;\nendmodule\n"
_STMT_TAIL_SRC = "module m;\n    wire a = b; // tail\nendmodule\n"


def test_midline_comment_inside_inline_rule_kept() -> None:
    """行中块注释落在 `inline = true` 规则上不得丢——挂 `inline` 槽随展开迁移。

    旧缺陷：槽挂 `inline_after`（锚 `=`）而规则节点被内联展开丢弃 → 注释消失
    （`assign` 走非 inline 路径所以既有断言没拦住）。
    """
    for fmt in (False, True):
        out = _run(_INLINE_RULE_MIDLINE_SRC, fmt)
        assert out.count("/* c */") == 1, f"[fmt={fmt}] 注释丢失/重复:\n{out}"
        assert "/* c */ b" in _norm(out), f"[fmt={fmt}] 注释不在原位:\n{out}"


def test_eol_comment_after_equal_kept_without_swallowing_semicolon() -> None:
    """`=` 后行尾注释（续行）保留，且不得吞掉语句终结符。

    旧缺陷：槽随内联展开迁到替身节点后，LineSuffix 落在替身节点 doc 末尾 →
    排在父布局的 `;` 之前，输出 `wire a = b // why;`（`;` 被注释吞掉，
    语法损坏）。现迁移时行终止型转 `leading`（注释后换行）。
    """
    for fmt in (False, True):
        out = _run(_INLINE_RULE_EOL_SRC, fmt)
        assert out.count("// why") == 1, f"[fmt={fmt}] 注释丢失/重复:\n{out}"
        assert "b;" in _norm(out), f"[fmt={fmt}] 终结符被注释吞掉:\n{out}"
        # 回读健康检查：产物再解析必须成立
        r2 = run_pipeline_on_source(
            source=out, rules_dir="grammar/verilog", quiet=True,
            no_lint=True, format_output=False, expand_macros=False,
        )
        assert r2["success"], f"[fmt={fmt}] 产物不可回读:\n{out}"


def test_statement_tail_comment_stays_on_statement_line() -> None:
    """语句尾注（`wire a = b; // tail`）仍在语句行尾（不被推成前置独立行）。

    回归护栏：行尾型槽的换槽只发生在内联展开迁移点——若在生产侧改判
    （读 `current_rule`，而它是内层规则退出后残留的旧值），尾注会被误挂
    `leading` 推到语句上方。
    """
    for fmt in (False, True):
        out = _run(_STMT_TAIL_SRC, fmt)
        line = next(l for l in out.splitlines() if "wire a = b;" in l)
        assert "// tail" in line, f"[fmt={fmt}] 尾注被推离语句行:\n{out}"

