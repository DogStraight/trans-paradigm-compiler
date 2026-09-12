"""宏 token 通配（ADR 0018 决策 2）：非空体宏在原子位当原子。

语言包零宏知识（不声明任何槽位）；合法性由 linter 的真展开检查兜底，
parser 只负责结构（分工见 docs/decisions/0018-parse-side-macro-placeholder.md）。
空体宏不走通配——它们由占位阶段改成 trivia 跳过（决策 0）。
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.usefixtures("config_loaded")


def _run(src: str, **kw) -> dict:
    return run_pipeline_on_source(source=src, quiet=True, no_lint=True, **kw)


def test_macro_in_expression_position_parses() -> None:
    """表达式位的宏（不展开）：通配当原子 → 解析成功，原文保留。"""
    src = "module m;\n  reg [7:0] a;\n  assign a = `SOMETHING;\nendmodule\n"
    res = _run(src, expand_macros=False)
    assert res["success"], res.get("error")
    assert "`SOMETHING" in res["output"]


def test_macro_node_appears_in_ast() -> None:
    """通配产出的宏节点在树中可见（MacroCall + 调用原文）。"""
    src = "module m;\n  reg [7:0] a;\n  assign a = `SOMETHING;\nendmodule\n"
    res = _run(src, expand_macros=False)
    assert res["success"], res.get("error")
    found: list = []

    def walk(n) -> None:
        if getattr(n, "node_name", None) == "MacroCall":
            found.append(n)
        for child in n.iter_children():
            walk(child)

    walk(res["ast"])
    assert [getattr(n, "_macro_fragment", "") for n in found] == ["`SOMETHING"]