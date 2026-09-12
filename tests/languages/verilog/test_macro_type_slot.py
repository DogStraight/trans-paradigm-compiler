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
Doc: docs/gaps/gap-preprocessor-macro-boundaries.md（条目 1）
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke

# 当前阻塞在**解析侧**（lint 已改吃真展开，见 `pipeline._stage_expand`）：
# 解析输入仍是锚形态，而锚在结构位（类型/关键字位）是普通标识符，无产生式
# 可匹配（实测 `input <锚> d;` → parse truncated）。解钕 = 目标态第 3/4 条：
# 解析输入改 raw + 引擎级宏占位协议（宏 token 满足当前位置任意元素），
# 锚收缩为空体宏专用。届时去掉本标记即可。
_XFAIL = pytest.mark.xfail(
    strict=True,
    reason="解析侧待宏占位协议：锚形态在结构位无产生式可匹配",
)


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
@_XFAIL
def test_type_position_macro_parses(src: str, name: str) -> None:
    """类型位宏：解析成功（无需任何语法槽位），且树中不出现宏专用节点。"""
    res = _run(src)
    assert res["success"], res.get("error")
    assert _find(res["ast"], "MacroCall") == []


@pytest.mark.parametrize("src", [_T, _NT, _PT], ids=["T", "NT", "PT"])
@_XFAIL
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
