"""注释文本里的"伪指令"与注释定界符识别（`.v` 真实语料事故回归守卫）。

背景（2026-09-17，两起真实事故）：
1. 块注释里写 `` `ifdef `` / `` `endif `` / `` `define `` 这类**文本**时，指令
   扫描按行首前缀识别 → 注释被当成指令 → 行被丢掉、注释被截断成未闭合
   （实测输出 `/* note\\nendmodule`，语法直接破坏，lint 报 125 错）。
2. 行注释内容含 `/*`（`//* group comb_simple`，ref_simcells.v 第 31 行）被当成
   块注释开启 → 之后 3783 行全被当成注释内部，指令全部失效。

处置：扫描前按语言包声明的注释标记推进行内/跨行状态——`kind = marker`
（`/* … */`）产生跨行状态；`kind = line`（`// … 换行`）行内终止，但其文本必须
跳过（其后的 `/*` 不算开启）。引擎不知道注释标点，标记全部来自
`[comment] pairs` / `[capture]`（`preprocessor._expand._load_comment_markers`）。

已知边界：注释之后的**同行**指令不识别（`/* c */ \\`define W 1`）——行首前缀
判定只认行首，且跨行标记扫描不产生"行首偏移"概念；实测现状保留原样不展开
（见 `test_directive_after_comment_same_line_left_verbatim`）。
"""

import pytest

from preprocessor._expand import scan_directives

_RULES = "grammar/verilog"


def _scan(src: str):
    """→ (宏表, 条件块列表, clean 源)。"""
    table, _funcs, conds, _holders, _dlines, clean, _c2r = scan_directives(
        src, _RULES
    )
    return table, conds, clean


class TestBlockCommentInterior:
    """块注释内部的伪指令文本：不是指令，注释原文逐字保留。"""

    def test_fake_directives_do_not_define_macros(self) -> None:
        src = "/*\n`endif\n`define X 1\n`ifdef Y\n*/\nmodule m();\nendmodule\n"
        table, conds, _ = _scan(src)
        assert table == {}
        assert conds == []

    def test_comment_text_kept_verbatim(self) -> None:
        """注释原文（含伪指令文本与结束定界符）逐字保留——不截断。"""
        src = "/* note\n`endif\n`define X 1\n*/\nmodule m();\nendmodule\n"
        _, _, clean = _scan(src)
        assert clean == src

    def test_real_directive_after_closed_comment_still_works(self) -> None:
        """注释闭合后同行/后续行的真指令照常生效（状态必须消亡）。"""
        src = "/* c */\n`define W 1\nmodule m();\nassign a = `W;\nendmodule\n"
        table, _, _ = _scan(src)
        assert table == {"W": "1"}


class TestLineCommentInterior:
    """行注释文本里的 `/*` 不算块注释开启（ref_simcells.v 事故）。"""

    def test_slash_star_in_line_comment_does_not_open_block(self) -> None:
        src = "//* group comb_simple\n`define W 1\nmodule m();\nendmodule\n"
        table, conds, _ = _scan(src)
        assert table == {"W": "1"}, "行注释里的 /* 不得吞掉后续指令"
        assert conds == []

    def test_line_comment_with_slash_star_many_times(self) -> None:
        """多次出现（真实语料每 20 行一次）同样不累积状态。"""
        src = (
            "//* group a\n"
            "module m();\n"
            "//* group b\n"
            "`ifdef X\n"
            "wire a;\n"
            "`endif\n"
            "//* group c\n"
            "endmodule\n"
        )
        _, conds, clean = _scan(src)
        assert len(conds) == 1, "块注释状态误开会让条件块与后续指令一起失效"
        assert "`ifdef X" not in clean


class TestRegressionControl:
    """真指令路径不受影响（对照）。"""

    def test_real_ifdef_still_creates_condition_block(self) -> None:
        src = "`define A 1\n`ifdef A\nmodule m();\nendmodule\n`endif\n"
        table, conds, _ = _scan(src)
        assert table == {"A": "1"}
        assert len(conds) == 1

    def test_directive_after_comment_same_line_left_verbatim(self) -> None:
        """已知边界：注释后**同行**指令不识别（行首前缀判定），原样保留。

        非回归项——修复前同样不识别；此断言锁定现状，避免"以为修了"。
        """
        src = "/* c */ `define W 1\nmodule m();\nendmodule\n"
        table, _, clean = _scan(src)
        assert table == {}
        assert "`define W 1" in clean

    @pytest.mark.parametrize("marker", ["/*", "*/"])
    def test_delimiter_in_string_documented_approximation(self, marker: str) -> None:
        """已知近似：字符串里的定界符形态会被当成注释标记（行级扫描不看字符串）。"""
        src = f'module m();\ninitial $display("{marker}");\n`define W 1\nendmodule\n'
        table, _, _ = _scan(src)
        # 现状：`/*` 开启跨行状态 → 后续 define 失效；`*/` 无开启语义 → 正常。
        assert table == ({} if marker == "/*" else {"W": "1"})
