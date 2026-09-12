"""宏落在类型位——**待外层展开机制支持**（当前 xfail，机制就位后翻正）。

需求（ADR-0017 验证 1/2）：`` input `NT d ``（NT=wire）/ `` output `PT q ``
（PT=reg [7:0]）/ `` input `T d ``（T=[7:0]）应解析成功，且树中出现宏节点
（宏名 + 源区间），与宏无关的节点照常产出，输出保留宏调用原文。

**当前有意不支持**（不是遗漏）：语言包不为宏保留语法槽位——宏位置本质上是
**文本任意**的，逐槽位声明 `@MacroCall` 既补不齐（结构词 / 运算符 / 分隔符位
根本没有槽位可声明；位置覆盖量化见 `_drafts/probe_macro_anywhere.py` 的
"任一 token 换成等价宏、输出不变"不变量），又会在 layout 自带字面量的槽位
静默错渲染（range 子槽会多套一对 `[]`）。

支持路径 = **外层（管线）展开 + 渲染侧 raw 拼接**（ADR-0017 决策 3）：展开后
`` input `NT d `` 就是 `input wire d`，语法包现有产生式直接成立，无需任何
槽位声明。届时去掉本文件的 xfail 标记即可。

Doc: docs/decisions/0017-macro-in-syntax-position.md（决策 3）
Doc: docs/gaps/gap-preprocessor-macro-boundaries.md（条目 1）
"""
import pytest

from pipeline import run_pipeline_on_source

pytestmark = pytest.mark.smoke

_XFAIL = pytest.mark.xfail(
    strict=True, reason="待外层展开 + 渲染侧 raw 拼接机制（ADR-0017 决策 3）"
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
def test_type_position_macro_parses_to_macro_node(src: str, name: str) -> None:
    """类型位宏：解析成功 + 树含 MacroCall（宏名 + 源区间切出宏调用原文）。"""
    res = _run(src)
    assert res["success"], res.get("error")
    calls = _find(res["ast"], "MacroCall")
    assert [c._macro_name for c in calls] == [name]
    node = calls[0]
    line, col, end_col = node._src_span
    assert src.split("\n")[line - 1][col:end_col] == f"`{name}"
    assert node._macro_fragment == f"`{name}"


@pytest.mark.parametrize("src", [_T, _NT, _PT], ids=["T", "NT", "PT"])
@_XFAIL
def test_type_position_macro_output_fidelity(src: str) -> None:
    """输出保真：宏调用原文回填，无锚残留。"""
    res = _run(src)
    assert res["success"], res.get("error")
    out = res["output"]
    assert "`__tpc_" not in out, out
    assert "tpc_marker" not in out, out


def test_hand_written_forms_unaffected() -> None:
    """手写形态不受影响（宏不在语法里，与宏无关的肯定路径必须一直是绿的）。"""
    src = "module m;\n  input wire [7:0] d;\n  output reg [7:0] q;\nendmodule\n"
    res = _run(src)
    assert res["success"], res.get("error")
    assert _find(res["ast"], "MacroCall") == []
    flat = " ".join(res["output"].split())
    assert "input wire [7:0] d;" in flat
    assert "output reg [7:0] q;" in flat
