"""宏体自带行尾注释时的展开路径回归（darkriscv 形态）。

形态：`` `define LUI 7'b01101_11 // lui rd,imm ``——宏体自带行尾注释，且宏调用
**同行还有内容**（`` ... ==`LUI; ``）。

钉住两件事：
1. 锚不进检查：展开后宏调用是锚（`` `<锚名> ``，macro token），linter 必须按
   锚表把它换成展开体（token 级窗口拼接），否则 P0 报未定义宏、管线失败。
2. 窗口拼接不跨 token 边界：宏调用后的 `;` 保留（文本级铺宏体会把同行后续
   内容吞进宏体注释里，实测 darkriscv 因此 81 条 phase-unrecognized 级联——
   真实语料上的守卫是 tests/e2e/test_real_corpus.py::test_file_parses_clean
   [ref_darkriscv.v]）。

Doc: linter/scanner.py::_splice_anchor_windows
Doc: docs/decisions/0017-macro-in-syntax-position.md
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke


def _run(src: str) -> dict:
    return run_pipeline_on_source(source=src, quiet=True, expand_macros=True)


def test_macro_body_trailing_comment_keeps_following_semicolon() -> None:
    """宏体带行尾注释，宏调用后的 `;` 不被吞（lint 零诊断 + 管线成功）。"""
    src = (
        "`define V 1'b1 // note\n"
        "module m;\n"
        "  wire a;\n"
        "  assign a = `V;\n"
        "endmodule\n"
    )
    res = _run(src)
    assert res["success"], res.get("error")
    assert "`V" in res["output"], res["output"]


def test_macro_body_comment_multi_use() -> None:
    """多处使用同一宏：每处都保留后续内容（不因首个命中而整体错位）。"""
    src = (
        "`define OP a == 7'b01101_11 // lui\n"
        "module m;\n"
        "  wire a, b, c;\n"
        "  assign b = `OP;\n"
        "  assign c = `OP;\n"
        "endmodule\n"
    )
    res = _run(src)
    assert res["success"], res.get("error")


def test_macro_body_without_comment_unaffected() -> None:
    """无注释宏体（既有形态）行为不变。"""
    src = (
        "`define V 1'b1\n"
        "module m;\n"
        "  wire a;\n"
        "  assign a = `V;\n"
        "endmodule\n"
    )
    res = _run(src)
    assert res["success"], res.get("error")
    assert "`V" in res["output"]
