"""模块体首注释渲染位置（渲染层注释漂移修复回归）。

缺陷：`ModuleDecl` 的 `sub_node` 首部 Comment 被 `join` 的"容器首部 Comment
拆段"逻辑（ADR-0013 B1.3）摘出前置 → 渲染到 `module` 声明**之前**（顶格）。
修法：拆段只作用于**非分段节点**（无 head/body/tail 的列表项）。

记录：`CHANGELOG.md`「修复：模块体首注释被渲染到 `module` 声明之前」。
"""

import pytest

from tests.e2e.run_pipeline import run_pipeline_on_source

pytestmark = [pytest.mark.smoke, pytest.mark.usefixtures("config_loaded")]

MIN = """module m(
    input clk,
    output reg [7:0] d
);
    // 注释 A
    // 注释 B
    sub_mod u_sub (
        .clk(clk),
        .d(d)
    );

    always @(posedge clk) begin
        d <= d + 1;
    end
endmodule
"""

MID = """module m(
    input clk,
    output reg [7:0] d
);
    assign d = 8'h00;
    // 注释 A
    // 注释 B
    sub_mod u_sub (
        .clk(clk),
        .d(d)
    );
endmodule
"""


def _run(src: str) -> list[str]:
    r = run_pipeline_on_source(source=src, quiet=True, no_lint=True)
    assert r["success"], r.get("error", "")
    return (r.get("output") or "").splitlines()


def _comment_lines(lines: list[str], text: str = "注释 A") -> list[int]:
    return [i for i, ln in enumerate(lines) if text in ln]


def test_body_head_comment_stays_inside_module() -> None:
    """模块体首元素是注释：渲染在 body 内、带缩进，不漂到 module 声明之前。"""
    lines = _run(MIN)
    mod_line = next(i for i, ln in enumerate(lines) if ln.startswith("module "))
    pos = _comment_lines(lines)
    assert pos, "注释丢失"
    assert pos[0] > mod_line, f"注释漂到 module 声明之前：{lines[:4]}"
    assert lines[pos[0]].startswith("    //"), f"注释缩进丢失：{lines[pos[0]]!r}"


def test_comment_after_member_unchanged() -> None:
    """对照：注释在成员之后（非首元素）——位置与缩进同样正确。"""
    lines = _run(MID)
    mod_line = next(i for i, ln in enumerate(lines) if ln.startswith("module "))
    pos = _comment_lines(lines)
    assert pos and pos[0] > mod_line
    assert lines[pos[0]].startswith("    //")


def test_idempotent_with_head_comment() -> None:
    """修复后 AST 不再被就地改动（旧实现 pop 注释）→ 幂等保持。"""
    r = run_pipeline_on_source(source=MIN, quiet=True, no_lint=True)
    assert r["success"], r.get("error", "")
    assert r.get("idempotent", True)
