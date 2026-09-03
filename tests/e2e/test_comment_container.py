"""tests/e2e/test_comment_container.py — 容器项间独占行注释进树门禁（ADR-0013 B1）。

repeat 列表容器（PortList / NamedPortList / DeclaratorList / CaseItemList）
迭代项之间的独占行注释（`input a, // State\n output b` 的组注释）此前走
line 通道时域回插（宏展开场景 only_tpc 不回普通注释 → 丢）；B1 后上浮为
Comment 迭代项进容器 items（结构序），renderer join 独立行段渲染。

断言策略（对 format 开/关两种模式 + 幂等）：
1. 每条注释文本出现在输出；
2. 独占行注释渲染为**独立行**（注释行只有注释，行首为 //），且行序源序
   正确（a 端口后 → b 端口前，不错位、不合并到代码行尾）；
3. AST 断言：容器 items 序列含 Comment 节点，位于对应端口/声明项之间；
4. 幂等：格式化的输出再次格式化不变。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport]

from tests.e2e.run_pipeline import run_pipeline_on_source  # noqa: E402

_MODULE_PORTS = (
    "module m (\n"
    "    input  wire a,\n"
    "    // State\n"
    "    output reg  b,\n"
    "    // Data\n"
    "    output wire c\n"
    ");\n"
    "endmodule\n"
)

_INST_PORTS = (
    "module top;\n"
    "    wire x, y;\n"
    "    sub u (\n"
    "        .clk (x),\n"
    "        // Control\n"
    "        .en  (y),\n"
    "        // Data\n"
    "        .q   (x)\n"
    "    );\n"
    "endmodule\n"
    "module sub(input clk, input en, output q);\n"
    "endmodule\n"
)

_DECLARATORS = (
    "module m;\n"
    "    wire a,\n"
    "    // group b\n"
    "    b, c;\n"
    "endmodule\n"
)

_CASE_ITEMS = (
    "module m;\n"
    "    reg [1:0] sel;\n"
    "    reg q;\n"
    "    always @* begin\n"
    "        case (sel)\n"
    "            2'b00: q = 1'b0;\n"
    "            // state one\n"
    "            2'b01: q = 1'b1;\n"
    "            // state two\n"
    "            default: q = 1'b0;\n"
    "        endcase\n"
    "    end\n"
    "endmodule\n"
)


def _run(src: str, fmt: bool):
    r = run_pipeline_on_source(
        source=src, rules_dir="grammar/verilog", quiet=True, no_lint=True,
        format_output=fmt, expand_macros=False,
    )
    assert r["success"], r.get("error", "")
    return r.get("output", ""), r.get("ast")


def _assert_comment_kept_standalone(out: str, text: str, fmt: str, after: str, before: str):
    """注释独立成行且位于 after 代码行之后、before 代码行之前。"""
    lines = out.splitlines()
    assert text in out, f"[{fmt}] 注释 {text!r} 丢失"
    ci = next(i for i, l in enumerate(lines) if text in l)
    cline = lines[ci].strip()
    assert cline.startswith("//"), f"[{fmt}] 注释 {text!r} 未独立成行: {lines[ci]!r}"
    # 注释行前是 after 代码行、后是 before 代码行
    assert any(after in l for l in lines[max(0, ci - 3):ci]), \
        f"[{fmt}] {text!r} 前的代码行不匹配 {after!r}: {lines[max(0, ci-3):ci]}"
    assert any(before in l for l in lines[ci + 1:ci + 4]), \
        f"[{fmt}] {text!r} 后的代码行不匹配 {before!r}: {lines[ci+1:ci+4]}"


def _assert_ast_items(ast, container: str, comments: list[str]):
    """AST 容器 items 含 Comment 节点且与端口项交错（源序）。"""
    from core.define import Node

    found = []

    def walk(n):
        if getattr(n, "node_name", None) == container:
            items = getattr(n, "items", None) or []
            seq = []
            for it in items:
                if getattr(it, "_comment", False):
                    seq.append("C:" + str(getattr(it, "value", ""))[:20])
                else:
                    seq.append(getattr(it, "node_name", "?"))
            found.append(seq)
        for c in list(getattr(n, "children", []) or []) + list(getattr(n, "sub_node", []) or []):
            walk(c)
        for v in vars(n).values():
            if isinstance(v, Node):
                walk(v)
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, Node):
                        walk(x)

    walk(ast)
    assert found, f"AST 中未找到 {container}"
    seq = found[0]
    assert any(s.startswith("C:") for s in seq), f"{container} items 无 Comment: {seq}"
    for c in comments:
        assert any(s == "C:" + c for s in seq), f"{container} items 缺 Comment {c!r}: {seq}"


class TestContainerGapComments:
    def test_module_port_list_comments(self):
        """PortList 项间独占注释：渲染独立行 + AST items 交错。"""
        for fmt in (False, True):
            out, ast = _run(_MODULE_PORTS, fmt)
            _assert_comment_kept_standalone(out, "// State", f"fmt={fmt}", "a,", "output")
            _assert_comment_kept_standalone(out, "// Data", f"fmt={fmt}", "b,", "output")
        _out, ast = _run(_MODULE_PORTS, True)
        _assert_ast_items(ast, "PortList", ["// State", "// Data"])

    def test_named_port_list_comments(self):
        """NamedPortList 实例端口组注释：独立行 + 不错位。"""
        for fmt in (False, True):
            out, ast = _run(_INST_PORTS, fmt)
            _assert_comment_kept_standalone(out, "// Control", f"fmt={fmt}", "clk", ".en")
            _assert_comment_kept_standalone(out, "// Data", f"fmt={fmt}", ".en", ".q")
        _out, ast = _run(_INST_PORTS, True)
        _assert_ast_items(ast, "NamedPortList", ["// Control", "// Data"])

    def test_declarator_list_comments(self):
        """DeclaratorList 声明器组注释：独立行（缩进随声明行）。"""
        for fmt in (False, True):
            out, ast = _run(_DECLARATORS, fmt)
            _assert_comment_kept_standalone(out, "// group b", f"fmt={fmt}", "a,", "b,")
        _out, ast = _run(_DECLARATORS, True)
        _assert_ast_items(ast, "DeclaratorList", ["// group b"])

    def test_case_item_comments(self):
        """CaseItemList 分支组注释：独立行 + 幂等。"""
        for fmt in (False, True):
            out, ast = _run(_CASE_ITEMS, fmt)
            _assert_comment_kept_standalone(out, "// state one", f"fmt={fmt}", "1'b0;", "2'b01")
            _assert_comment_kept_standalone(out, "// state two", f"fmt={fmt}", "1'b1;", "default")
        _out, ast = _run(_CASE_ITEMS, True)
        _assert_ast_items(ast, "CaseItemList", ["// state one", "// state two"])

    def test_idempotent(self):
        """格式化输出再次格式化不变（结构序注释不漂移不重复）。"""
        for src in (_MODULE_PORTS, _INST_PORTS, _DECLARATORS, _CASE_ITEMS):
            out1, _ = _run(src, True)
            out2, _ = _run(out1, True)
            assert out1 == out2, "格式化输出不幂等"
            # 注释不重复
            for c in ("// State", "// Control", "// group b", "// state one"):
                if c in out1:
                    assert out1.count(c) == 1, f"{c!r} 重复出现: {out1.count(c)} 次"


_BLOCK_END = (
    "module m;\n"
    "    reg [1:0] sel;\n"
    "    reg q;\n"
    "    always @* begin\n"
    "        case (sel)\n"
    "            2'b00: begin\n"
    "                q = 1'b0;\n"
    "            end // case zero\n"
    "            2'b01: begin\n"
    "                q = 1'b1;\n"
    "            end // case one\n"
    "            default: q = 1'b0;\n"
    "        endcase\n"
    "    end\n"
    "endmodule\n"
)


class TestBlockEndComments:
    """块结束符（end/endcase 等）后行尾注释进树（ADR-0013：块结束符行尾
    注释挂块规则节点 trailing 槽，结构序渲染——此前只记 inline anchor，
    restore 只回 midline/tpc 不回行尾普通注释 → 丢失，tv80 实测 134 条）。"""

    def test_end_line_comment_kept(self):
        """`end // case zero` 行尾注释保留在 end 行尾（format 开/关）。"""
        for fmt in (False, True):
            out, ast = _run(_BLOCK_END, fmt)
            lines = out.splitlines()
            for c in ("case zero", "case one"):
                assert c in out, f"[fmt={fmt}] 注释 {c!r} 丢失"
                ci = next(i for i, l in enumerate(lines) if c in l)
                assert lines[ci].strip().startswith("end //"), \
                    f"[fmt={fmt}] {c!r} 未锚定 end 行尾: {lines[ci]!r}"

    def test_block_end_comment_idempotent(self):
        """格式化输出再次格式化不变。"""
        out1, _ = _run(_BLOCK_END, True)
        out2, _ = _run(out1, True)
        assert out1 == out2
        assert out1.count("case zero") == 1
        assert out1.count("case one") == 1
