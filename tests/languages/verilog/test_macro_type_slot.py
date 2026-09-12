"""宏落在类型位（`` input `NT d `` / `` output `PT q `` / `` input `T d ``）。

**语言包不为宏保留语法槽位**（ADR-0017 决策 2）：宏位置本质上是**文本任意**
的，逐槽位声明 `@MacroCall` 既补不齐（结构词 / 运算符 / 分隔符位根本没有槽位
可声明），又会在 layout 自带字面量的槽位静默错渲染（range 子槽会多套一对
`[]`）。位置覆盖量化见 `tools/check_macro_coverage.py` 的不变量：“任一 token
换成等价宏、输出不变”。

linter 侧吃**真展开态**（反向解析器看真语法结构）：展开后 `` input `NT d ``
就是 `input wire d`，现有产生式直接成立——锚形态在类型位是普通标识符，
无产生式可匹配（曾在此处误报）。

Doc: docs/decisions/0017-macro-in-syntax-position.md（决策 2/3/4）
Doc: docs/gaps/gap-parser-linter-approximation.md（linter 近似面）；CHANGELOG.md（解析侧切真展开）
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke



def _find(node, name: str) -> list:
    out: list = []

    def rec(n):
        if getattr(n, "node_name", None) == name:
            out.append(n)
        for child in n.iter_children():
            rec(child)

    rec(node)
    return out


def _run(src: str, **kw) -> dict:
    return run_pipeline_on_source(source=src, quiet=True, expand_macros=True, **kw)


# 三种形态：宏体分别覆盖 net 类型 / 类型 + 位宽 / 纯位宽
_T = "`define T [7:0]\nmodule m;\n  input `T d;\nendmodule\n"
_NT = "`define NT wire\nmodule m;\n  input `NT d;\nendmodule\n"
_PT = "`define PT reg [7:0]\nmodule m;\n  output `PT q;\nendmodule\n"


@pytest.mark.parametrize(
    "src,name", [(_T, "T"), (_NT, "NT"), (_PT, "PT")], ids=["T", "NT", "PT"]
)
def test_type_position_macro_parses(src: str, name: str) -> None:
    """类型位宏：解析成功（无需任何语法槽位），且树中不出现宏专用节点。"""
    res = _run(src)
    assert res["success"], res.get("error")
    assert _find(res["ast"], "MacroCall") == []


@pytest.mark.parametrize("src", [_T, _NT, _PT], ids=["T", "NT", "PT"])
def test_type_position_macro_output_fidelity(src: str) -> None:
    """输出保真：宏调用原文回填，无锚残留，且整个输出**幂等**。"""
    res = _run(src)
    assert res["success"], res.get("error")
    out = res["output"]
    assert "`__tpc_" not in out, out
    assert "tpc_marker" not in out, out
    name = src.split("\n")[0].removeprefix("`define ").split(" ")[0]
    assert f"`{name}" in out, out
    again = _run(out)
    assert again["success"], again.get("error")
    assert again["output"] == out, (out, again["output"])


def test_hand_written_forms_unaffected() -> None:
    """手写形态不受影响（宏不在语法里，与宏无关的肯定路径必须一直是绿的）。"""
    src = "module m;\n  input wire [7:0] d;\n  output reg [7:0] q;\nendmodule\n"
    res = _run(src)
    assert res["success"], res.get("error")
    assert _find(res["ast"], "MacroCall") == []
    flat = " ".join(res["output"].split())
    assert "input wire [7:0] d;" in flat
    assert "output reg [7:0] q;" in flat
