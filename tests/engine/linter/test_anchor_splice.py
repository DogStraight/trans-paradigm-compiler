"""锚窗口拼接（linter 展开路径检查）——锚不进检查、展开体进检查。

Doc: linter/scanner.py::_splice_anchor_windows
Doc: docs/decisions/0017-macro-in-syntax-position.md
"""

import pytest

from core.define import DEFAULT_EXT_DIRS, DEFAULT_RULES_DIR
from core.token_protocol import anchor_name, anchor_salt
from preprocessor._expand import _load_config

MACRO_PREFIX, _ = _load_config()


@pytest.fixture(scope="module")
def scanner():
    from linter.scanner import LinterScanner

    return LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)


def _anchor(seq: int, body: str) -> tuple[str, list[dict]]:
    """构造一条 token 锚（形态同 preprocessor/_expand 产出）。"""
    marker = f"{MACRO_PREFIX}{anchor_name(seq, anchor_salt('unit'))}"
    entry = {
        "marker": marker,
        "fragment": f"{MACRO_PREFIX}NAME",
        "mode": "token",
        "kind": "macro",
        "body": body,
    }
    return marker, [entry]


class TestAnchorNotCheckedExpansionChecked:
    """锚本身不是用户宏（不得报未定义宏）；锚代表的展开体必须被检查。"""

    def test_anchor_alone_reported_undefined(self, scanner) -> None:
        """不传锚表：锚是 macro token 又不在宏表 → 报未定义宏（P0 语义正确）。"""
        marker, _ = _anchor(1, "wire")
        src = f"module m;\n  input {marker} d;\nendmodule\n"
        codes = {d.code for d in scanner.scan(src)}
        assert "undefined-macro" in codes

    def test_anchor_with_table_not_reported(self, scanner) -> None:
        """传锚表：锚被展开体替换 → 不再是未定义宏。"""
        marker, anchors = _anchor(1, "wire")
        src = f"module m;\n  input {marker} d;\nendmodule\n"
        codes = {d.code for d in scanner.scan(src, anchors=anchors)}
        assert "undefined-macro" not in codes

    def test_expansion_body_is_checked(self, scanner) -> None:
        """检查对象是展开体：展开体合法 → 零诊断；不合法 → 报诊断。"""
        marker, anchors = _anchor(1, "wire")
        src = f"module m;\n  input {marker} d;\nendmodule\n"
        assert scanner.scan(src, anchors=anchors) == []

        bad_marker, bad_anchors = _anchor(2, "wire wire wire")
        bad_src = f"module m;\n  input {bad_marker} d;\nendmodule\n"
        assert scanner.scan(bad_src, anchors=bad_anchors) != []


class TestWindowCarriesSyntaxTokensOnly:
    """窗口只带展开体的语法 token：注释不进窗口（trivia 对语法检查无贡献）。"""

    def test_body_comment_not_in_window(self, scanner) -> None:
        marker, anchors = _anchor(3, "1'b1 // note")
        # 若注释进了窗口，宏调用后的 `;` 会被视作..."不影响 token 级拼接"；
        # 此处直接断言拼接结果里没有 comment token。
        from core.define import Token

        toks = [
            Token(content=marker, type="macro.call", line=3, column=10),
        ]
        out = scanner._splice_anchor_windows(toks, anchors)
        assert [t.type for t in out] == ["literal.number"]
        assert out[0].content == "1'b1"

    def test_body_comment_does_not_break_statement(self, scanner) -> None:
        """宏体带行尾注释：宏调用**同行的后续 token** 不被吞（darkriscv 形态）。"""
        marker, anchors = _anchor(4, "1'b1 // lui")
        src = f"module m;\n  wire a;\n  assign a = {marker};\nendmodule\n"
        assert scanner.scan(src, anchors=anchors) == []


class TestWindowPositionMapping:
    """展开体 token 位置映射到锚位置（诊断落点 = 锚位置）。"""

    def test_tokens_rebased_to_anchor(self, scanner) -> None:
        from core.define import Token

        marker, anchors = _anchor(5, "wire [7:0]")
        toks = [Token(content=marker, type="macro.call", line=42, column=17)]
        out = scanner._splice_anchor_windows(toks, anchors)
        # 体为单行 → 全部 token 落在锚所在行；体首 token 列偏移到锚列
        assert {t.line for t in out} == {42}
        assert out[0].column == 17
        assert any(t.content == "wire" for t in out)
        assert all(t.content != marker for t in out)


class TestConservativeFallbacks:
    """保守回退：信息不足时不静默丢内容。"""

    def test_unlexable_body_keeps_anchor(self, scanner) -> None:
        from core.define import Token

        marker, anchors = _anchor(6, "")
        anchors[0]["body"] = ""  # 空体不建窗口（_expand 走 inline/line 锚）
        toks = [Token(content=marker, type="macro.call", line=1, column=0)]
        out = scanner._splice_anchor_windows(toks, anchors)
        assert out == toks

    def test_no_anchors_returns_same_stream(self, scanner) -> None:
        from core.define import Token

        toks = [Token(content="id", type="id", line=1, column=0)]
        assert scanner._splice_anchor_windows(toks, []) is toks

    def test_non_token_modes_ignored(self, scanner) -> None:
        from core.define import Token

        toks = [Token(content="id", type="id", line=1, column=0)]
        anchors = [
            {"marker": "tpc:macro:1", "fragment": "x", "mode": "inline", "body": "y"}
        ]
        assert scanner._splice_anchor_windows(toks, anchors) is toks
