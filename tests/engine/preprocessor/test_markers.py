"""tpc marker 书写/识别（`preprocessor/_markers.py`）——注释标点声明驱动。

marker 以**注释形态**穿过管线（parser 当 trivia、渲染端保留注释），所以
书写形态 = 语言的注释标点（语言包声明）+ 引擎自有的 `<tpc:kind:seq>` 包装。
本测试覆盖：书写（含缺形态时 fail-fast）、整行形态识别、还原侧按声明的标点
定位（用 yaml 的 `#` 证明还原不是"按 verilog 硬编码"）。
"""

import pytest

from lexer.comment_syntax import load_comment_syntax
from preprocessor._bridge import restore_anchors
from preprocessor._markers import (
    inline_marker,
    line_form_re,
    line_marker,
    marker_core_re,
)

_VERILOG = "grammar/verilog"
_YAML = "grammar/yaml"
_C4 = "grammar/c4"


class TestWriteMarker:
    """书写：标点来自声明，缺形态 fail-fast（不静默降级）。"""

    def test_line_marker_verilog(self) -> None:
        s = load_comment_syntax(_VERILOG)
        assert line_marker(s, "tpc:cond:0") == "// <tpc:cond:0>"

    def test_line_marker_yaml(self) -> None:
        """同一条占位在 yaml 里写成 `# <…>`——形态随语言包变。"""
        s = load_comment_syntax(_YAML)
        assert line_marker(s, "tpc:cond:0") == "# <tpc:cond:0>"

    def test_inline_marker_verilog(self) -> None:
        s = load_comment_syntax(_VERILOG)
        assert inline_marker(s, "tpc:macro:7") == "/*<tpc:macro:7>*/"

    @pytest.mark.parametrize("rules_dir", [_YAML, _C4])
    def test_inline_marker_without_block_comment_fails(self, rules_dir: str) -> None:
        """未声明块注释的语言包（yaml/c4）要写行内占位 → 直接报错。"""
        s = load_comment_syntax(rules_dir)
        with pytest.raises(ValueError, match="成对注释定界符"):
            inline_marker(s, "tpc:macro:0")


class TestLineFormPattern:
    """整行形态识别：只认本语言的占位形态，且必须独占整行。"""

    def test_matches_own_form_only(self) -> None:
        v = line_form_re(load_comment_syntax(_VERILOG))
        y = line_form_re(load_comment_syntax(_YAML))
        assert v.match("// <tpc:cond:0>")
        assert not v.match("# <tpc:cond:0>")
        assert y.match("# <tpc:cond:0>")
        assert not y.match("// <tpc:cond:0>")

    def test_leading_indent_and_trailing_space_ok(self) -> None:
        v = line_form_re(load_comment_syntax(_VERILOG))
        m = v.match("    // <tpc:macro:3>  ")
        assert m and m.group(1) == "tpc:macro:3"

    def test_code_after_marker_not_a_line_form(self) -> None:
        """占位后还有内容 → 不是"独占整行"占位（那是行内形态的场景）。"""
        v = line_form_re(load_comment_syntax(_VERILOG))
        assert v.match("// <tpc:macro:3> wire a;") is None

    def test_marker_core_extracted_from_any_text(self) -> None:
        m = marker_core_re().search("x /*<tpc:macro:12>*/ y")
        assert m and m.group(1) == "tpc:macro:12"


class TestRestoreFollowsDeclaration:
    """还原侧按声明的标点定位（不是"只认 verilog 的 `//`"）。"""

    def _anchors(self, marker: str, text: str) -> list[dict]:
        return [{"marker": marker, "source_text": text, "mode": "line", "kind": "cond"}]

    def test_line_restore_with_yaml_hash(self) -> None:
        out = restore_anchors(
            "a: 1\n# <tpc:cond:0>\nb: 2\n",
            self._anchors("tpc:cond:0", "c: 3\n"),
            syntax=load_comment_syntax(_YAML),
        )
        assert out == "a: 1\nc: 3\n\nb: 2\n"
        assert "tpc:" not in out

    def test_line_restore_verilog(self) -> None:
        # 整行形态含前导缩进 → 整行（含缩进）换回原文段
        out = restore_anchors(
            "wire a;\n  // <tpc:cond:0>\nwire b;\n",
            self._anchors("tpc:cond:0", "`ifdef X\n`endif\n"),
            syntax=load_comment_syntax(_VERILOG),
        )
        assert out == "wire a;\n`ifdef X\n`endif\n\nwire b;\n"
        assert "tpc:" not in out

    def test_line_restore_broken_line_fallback(self) -> None:
        """占位被并进别的行（非独占）→ 退化为文本替换，不残留 marker。"""
        out = restore_anchors(
            "wire a; // <tpc:cond:0>\n",
            self._anchors("tpc:cond:0", "`ifdef X"),
            syntax=load_comment_syntax(_VERILOG),
        )
        assert out == "wire a; `ifdef X\n"
        assert "tpc:" not in out

    def test_inline_restore_verilog_block_form(self) -> None:
        anchors = [
            {
                "marker": "tpc:macro:0",
                "source_text": "`W",
                "mode": "inline",
                "kind": "macro",
                "body": "",
            }
        ]
        out = restore_anchors(
            "wire a = /*<tpc:macro:0>*/;\n",
            anchors,
            syntax=load_comment_syntax(_VERILOG),
        )
        assert out == "wire a = `W;\n"
