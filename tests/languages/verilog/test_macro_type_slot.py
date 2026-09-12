"""宏落在类型位（语法位）——parser 直产 MacroCall 节点，不硬解析宏内容。

ADR-0017 验证 1/2 的闸门：`` input `NT d ``（NT=wire）/ `` output `PT q ``
（PT=reg [7:0]）/ `` input `T d ``（T=[7:0]）解析成功，树中出现宏节点（宏名 +
源区间），与宏无关的节点照常产出，输出保留宏调用原文。

Doc: docs/decisions/0017-macro-in-syntax-position.md（决策 2/3）
Doc: grammar/verilog/02_declarations/00_base.toml（TypeSpec/TypeSpecNoReg 槽位）
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
    return run_pipeline_on_source(
        source=src, quiet=True, expand_macros=True, **kw
    )


# 三种形态：宏体分别覆盖 net 类型 / 类型 + 位宽 / 纯位宽
_T = "`define T [7:0]\nmodule m;\n  input `T d;\nendmodule\n"
_NT = "`define NT wire\nmodule m;\n  input `NT d;\nendmodule\n"
_PT = "`define PT reg [7:0]\nmodule m;\n  output `PT q;\nendmodule\n"


@pytest.mark.parametrize(
    "src,name", [(_T, "T"), (_NT, "NT"), (_PT, "PT")], ids=["T", "NT", "PT"]
)
def test_type_position_macro_parses_to_macro_node(src: str, name: str) -> None:
    """类型位宏：解析成功 + 树含 MacroCall（宏名 + 源区间切出宏调用原文）。"""
    res = _run(src)
    assert res["success"], res.get("error")
    calls = _find(res["ast"], "MacroCall")
    assert [c._macro_name for c in calls] == [name]
    node = calls[0]
    assert node._src_span is not None
    line, col, end_col = node._src_span
    assert src.split("\n")[line - 1][col:end_col] == f"`{name}"
    assert node._macro_fragment == f"`{name}"


@pytest.mark.parametrize("src", [_T, _NT, _PT], ids=["T", "NT", "PT"])
def test_type_position_macro_output_fidelity(src: str) -> None:
    """输出保真：宏调用原文回填，无锚残留。"""
    out = _run(src)["output"]
    assert "`__tpc_" not in out, out
    assert "tpc_marker" not in out, out


def test_unrelated_nodes_still_produced() -> None:
    """无关部分照常产出：模块名/端口名/方向等节点不因宏位而丢失。"""
    res = _run(_PT)
    assert {n.node_name for n in _find(res["ast"], "ModuleDecl")} == {"ModuleDecl"}
    assert {n.content for n in _find(res["ast"], "Identifier")} == {"m", "q"}
    # 端口的字段照常绑定（方向 + 宏节点 + 声明器）
    decl = _find(res["ast"], "BodyOutputDecl")
    assert len(decl) == 1 and decl[0].direction == "output"
    assert "`PT" in res["output"]


def test_linter_checks_expansion_not_anchor() -> None:
    """linter 检查展开形态：`` input `NT d `` 展开为 `input wire d` → 零诊断。"""
    from core.define import DEFAULT_EXT_DIRS, DEFAULT_RULES_DIR
    from linter.scanner import LinterScanner

    scanner = LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)
    assert scanner.scan(_NT) == []
    assert scanner.scan(_PT) == []


def test_hand_written_forms_unaffected() -> None:
    """手写形态不受影响：无宏 → 无 MacroCall 节点，类型/位宽照常渲染。"""
    src = "module m;\n  input wire [7:0] d;\n  output reg [7:0] q;\nendmodule\n"
    res = _run(src)
    assert res["success"], res.get("error")
    assert _find(res["ast"], "MacroCall") == []
    flat = " ".join(res["output"].split())
    assert "input wire [7:0] d;" in flat
    assert "output reg [7:0] q;" in flat


def test_macro_in_sub_slot_not_supported() -> None:
    """已知边界：**宏子槽**（`` input wire `T d ``，T=[7:0]）不做。

    子槽 layout 自带字面 `[` `]`，而宏残片可能含方括号 → 会多套一对（静默错
    渲染）。宁可停不可静默错：保持解析失败。若将来支持，须同时解决该槽位的
    渲染（见 gap-preprocessor-macro-boundaries 登记）。
    """
    src = "`define T [7:0]\nmodule m;\n  input wire `T d;\nendmodule\n"
    assert _run(src)["success"] is False
