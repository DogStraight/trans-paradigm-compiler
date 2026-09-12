"""宏体自带行尾注释时的展开路径回归（darkriscv 形态）。

形态：`` `define LUI 7'b01101_11 // lui rd,imm ``——宏体自带行尾注释，且宏调用
**同行还有内容**（`` ... ==`LUI; ``）。

钉住的不变量：**宏调用同行的后续内容不被吞**（输出保留 `;`、管线成功）。
它是**外层展开路线（ADR-0017 决策 3）的迁移守卫**：文本级铺宏体会跨注释边界，
把宏调用同行的 `;` 落进宏体注释里 → 语句丢分号 → 发现器级联失守（darkriscv 实测
81 条 `phase-unrecognized`）。谁改走文本展开而不做 raw 拼接，这里会红。

当前实现（锚 + `restore_anchors`）天然满足该不变量——锚不会把宏体铺进文本。

Doc: docs/decisions/0017-macro-in-syntax-position.md（决策 3/4）
Doc: preprocessor/_expand.py（宏体末行注释补换行，防吞调用同行后续 token）
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
