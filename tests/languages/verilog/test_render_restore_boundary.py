"""tests/languages/verilog/test_render_restore_boundary.py — 渲染/还原边界回归。

两个真实缺陷的固化断言（2026-09-17 darkriscv interop 探查）：
  1. **还原原文不经 formatter**：`format_generated` 必须在 restore **之前**
     跑——restore 后文本带回 `ifdef` 指令行与未展开宏引用，无预处理器的
     Verilog formatter 会把声明打散（`reg [31:0] X [0:(2**`TH)-1]; // c`
     → `reg X // c [0:...]`，`;` 落进注释 → 输出语法非法）。
  2. **行尾注释不得吞掉同行后续元素**：列表末项的行尾注释属声明为"到行边界
     终止"型（语言包 `[comment] pairs` 的 kind = line）时，同行后续布局元素
     （模块端口收尾 `);`）必须另起一行——否则回读时被并入注释文本。

两断言都跑 format 开/关两模式（世界 A 渲染原样 + e2e 默认 formatter 路径）。
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


# ── ① 还原原文不经 formatter ──

_IFDEF_SRC = (
    "module m;\n"
    "`ifdef TH\n"
    "    reg [31:0] IFPC [0:(2**`TH)-1];   // stage\n"
    "`else\n"
    "    reg [31:0] IFPC;                  // state\n"
    "`endif\n"
    "endmodule\n"
)


def test_condition_block_restored_text_verbatim() -> None:
    """`TH` 未定义 → ifdef 分支折叠为占位、还原时原文逐字落回（不过 formatter）。

    旧缺陷（formatter 跑在 restore 之后）：`reg [31:0] IFPC [0:(2**`TH)-1];`
    被打散成 `reg  IFPC // stage [0:...]`（`;` 落进注释）。
    """
    out = _run(_IFDEF_SRC, True)
    assert "reg [31:0] IFPC [0:(2**`TH)-1];" in out, out
    assert "2**`TH)-1] stage" not in out, f"还原原文被 formatter 打散:\n{out}"


def test_condition_block_restored_text_verbatim_format_off() -> None:
    """format 关：同一不变式（两模式一致 = 差异只在 formatter 是否跑）。"""
    out = _run(_IFDEF_SRC, False)
    assert "reg [31:0] IFPC [0:(2**`TH)-1];" in out, out


# ── ② 行尾注释不得吞掉同行后续元素 ──

_PORT_SRC = (
    "module m #(parameter P = 0)(\n"
    "    input a,\n"
    "    output [3:0] B // tail comment\n"
    ");\n"
    "endmodule\n"
)


def _code_after_line_comment(out: str) -> list[str]:
    """含 `//` 且注释文本后还有收尾符的行（吞码现场）。"""
    return [
        ln for ln in out.split("\n")
        if (i := ln.find("//")) >= 0 and ln[i:].rstrip().endswith(");")
    ]


def test_port_close_not_swallowed_by_line_comment() -> None:
    """末端口行尾注释后不得再拼 `);`（旧缺陷：`... :) );` → 端口表未闭合）。"""
    for fmt in (False, True):
        out = _run(_PORT_SRC, fmt)
        assert "// tail comment" in out, f"[fmt={fmt}] 注释丢失: {out}"
        assert ");" in out, f"[fmt={fmt}] 收尾符丢失: {out}"
        bad = _code_after_line_comment(out)
        assert not bad, f"[fmt={fmt}] 行注释吞掉收尾符: {bad}"


def test_block_comment_may_stay_inline() -> None:
    """块注释（声明 kind = marker）不需断行——不得被当成行注释强制断行。"""
    src = _PORT_SRC.replace("// tail comment", "/* block */")
    for fmt in (False, True):
        out = _run(src, fmt)
        assert "/* block */" in out, out
        assert ");" in out, out
