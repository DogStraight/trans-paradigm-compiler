"""跨行块注释的内部行缩进（缩进 pass 规范化 + 渲染端逐字输出的配合）。

背景（2026-09-17）：渲染端对注释是**逐字输出**（`[Comment.renderer.layout]
ref = "value"`）——注释首行随布局缩进落到目标列，内部行仍是**源缩进**，两者的
相对偏移随环境变化（源 2 → 目标 4 时偏移已被破坏）。缩进 pass 若按
`scope_depth` 重算内部行，会把 ` *` 前的对齐空格吃掉（真实语料版权头退化为
`* ...`）。

处置：内部段（`LineContext.is_comment_cont`）按注释自身惯例规范化——
  - 以 `*` 开头（`/* * */` 风格）→ 对齐到**块首行缩进 + 1**（星号对齐 `/*`
    的星号），与源内偏移无关；`*/` 同理；
  - 其余（自由文本，如 ASCII 图）→ 按块首行平移量整体平移，保自身版式。
规范化是幂等的（二次格式化不变）。

Doc: grammar/verilog/plugins/formatter/passes/indent.py::run_indent_pass
Doc: grammar/verilog/plugins/formatter/boundary.py::LineContext.is_comment_cont
"""

import importlib
import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)  # noqa: E402
importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

from grammar.verilog.plugins.formatter.boundary import LineContext  # noqa: E402
from grammar.verilog.plugins.formatter.passes.indent import (  # noqa: E402
    run_indent_pass,
)
from pipeline import run_pipeline_on_source  # noqa: E402

pytestmark = pytest.mark.usefixtures("config_loaded")


def _ctx(line_no: int, depth: int = 0, cont: bool = False) -> LineContext:
    """行上下文：注释首行用 cont=False，内部段用 cont=True。"""
    return LineContext(
        line_number=line_no,
        text="",
        scope_depth=depth,
        is_comment_cont=cont,
    )


def _run_pass(lines: list[str], contexts: list[LineContext]) -> list[str]:
    return run_indent_pass(lines, contexts, indent_width=4)


def _format(src: str) -> str:
    r = run_pipeline_on_source(
        source=src,
        rules_dir="grammar/verilog",
        quiet=True,
        no_lint=True,
        format_output=True,
        expand_macros=True,
    )
    assert r["success"], r.get("error", "")
    return r.get("output", "")


class TestStarLinesAlignToOpener:
    """`*` 开头行对齐到块首行 + 1（与源内偏移无关）。"""

    def test_star_and_closer_align_to_opener(self) -> None:
        lines = ["", "    /* note", "   * aligned", "   */"]
        out = _run_pass(
            lines,
            [
                _ctx(2, depth=1),
                _ctx(3, depth=1, cont=True),
                _ctx(4, depth=1, cont=True),
            ],
        )
        assert out[1] == "    /* note"
        assert out[2] == "     * aligned"
        assert out[3] == "     */"

    def test_contexts_out_of_line_order(self) -> None:
        """内部段 ctx 可能先于首行 ctx 产出（boundary 拆分时先吐内部行）。"""
        lines = ["  /* note", " * x", " */"]
        contexts = [
            _ctx(3, depth=1, cont=True),
            _ctx(2, depth=1, cont=True),
            _ctx(1, depth=1),
        ]
        out = _run_pass(lines, contexts)
        assert out == ["    /* note", "     * x", "     */"]

    def test_star_line_keeps_inner_spacing(self) -> None:
        """只重写行首空白——`*` 之后的文本（缩进型清单项）原样保留。"""
        lines = ["/*", " * Copyright", " *   - item", " */"]
        out = _run_pass(
            lines,
            [
                _ctx(1),
                _ctx(2, cont=True),
                _ctx(3, cont=True),
                _ctx(4, cont=True),
            ],
        )
        assert out == [
            "/*",
            " * Copyright",
            " *   - item",
            " */",
        ]


class TestFreeTextLinesShift:
    """非 `*` 开头（自由文本）按块首行平移量整体平移。"""

    def test_free_text_shifted_by_opener_delta(self) -> None:
        lines = ["/* +---+", "   | x |", "   +---+ */"]
        contexts = [_ctx(1), _ctx(2, cont=True), _ctx(3, cont=True)]
        # 首行在此深度下被重算为 4 空格（末行为模块外），平移量 = 4 − 0
        out = run_indent_pass(
            lines,
            [LineContext(1, "", scope_depth=1), *contexts[1:]],
            indent_width=4,
        )
        shift = len(out[0]) - len(lines[0])
        assert out[1] == " " * (3 + shift) + "| x |"
        assert out[2] == " " * (3 + shift) + "+---+ */"


class TestEndToEnd:
    """真实管线（渲染 + 格式化）下的块注释版式。"""

    def test_module_comment_reindented_as_block(self) -> None:
        src = "module m;\n  /* note\n   * aligned\n   */\n  wire a;\nendmodule\n"
        out = _format(src)
        assert ("    /* note\n" "     * aligned\n" "     */\n") in out

    def test_copyright_header_star_alignment_kept(self) -> None:
        """版权头是 `/*` 顶格 + ` *` 星号对齐——不得退化成 `* ...`。"""
        src = (
            "/*\n"
            " * Copyright (c) 2024\n"
            " *   - item\n"
            " */\n"
            "module m();\n"
            "endmodule\n"
        )
        out = _format(src)
        assert out.startswith("/*\n * Copyright (c) 2024\n *   - item\n */\n")

    def test_comment_with_directive_text_kept(self) -> None:
        """注释内含伪指令文本：内容逐字保留（与预处理器修复同一条链）。"""
        src = "/*\n`endif\n`define W 1\n*/\nmodule m();\nendmodule\n"
        out = _format(src)
        assert "`endif" in out and "`define W 1" in out

    @pytest.mark.parametrize(
        "src",
        [
            "/* note\n * aligned\n */\nmodule m();\nendmodule\n",
            "module m;\n  /* note\n   * aligned\n   */\n  wire a;\nendmodule\n",
            "module m;\n  initial begin\n      /* note\n       * a\n       */\n"
            "    x = 1;\n  end\nendmodule\n",
            "/*\n * Copyright (c) 2024\n */\nmodule m();\nendmodule\n",
        ],
    )
    def test_format_idempotent(self, src: str) -> None:
        once = _format(src)
        assert _format(once) == once
