"""e2e Macro 测试组——统一位置桥（token/line 锚 + 残片消耗式）还原回归守卫。

背景：宏还原从"同步词启发式 find(body)"升级为统一位置桥——展开时把宏调用
替换为唯一 token（tpc_marker_N，随 AST 确定渲染）或整行占位（line 锚，
行首空体 decl 修饰如 `FORMAL_KEEP），还原时按操作栈 + 原文残片精确回插。
本测试把 macro 样本组的还原效果固化为断言，防止还原机制回退。

覆盖：
- 所有 macro 样本管线成功、无 token/marker 残留
- function-like 宏调用还原（`MIN/`MAX/`debug）
- object-like 宏调用还原（`W/`BW 多宏）
- 条件块占位还原（`ifdef/`else/`endif）
- 简单样本保真度阈值

已知边界（部分还原，仅断言成功+无残留，后续逐步完善）：
- ref_timescale：`timescale 指令保真度低，但根因在 parser 层（空参数模块 #()
  + 空 always 渲染丢 input 端口），与预处理器还原无关（expand_macros=False
  同样丢失），属语法/渲染层待办。
"""

import os
import sys
import io
import contextlib
import difflib

import pytest

# 项目根 + stdout UTF-8（必须在 import core 之前）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
from tests import _bootstrap  # noqa: E402

from tests.e2e.run_pipeline import run_pipeline_on_source  # noqa: E402

_MACRO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "macro")
_REF_DIR = os.path.join(_MACRO_DIR, "ref")

# 所有 macro 样本
_MACRO_CASES = sorted(
    f for f in os.listdir(_REF_DIR) if f.endswith(".v") and not f.startswith("_")
)

# 保真度阈值组：复杂/边界样本只断言成功+无残留
_BOUNDARY_CASES = {"ref_timescale.v"}
_FIDELITY_CASES = [f for f in _MACRO_CASES if f not in _BOUNDARY_CASES]
_FIDELITY_THRESHOLD = 0.80


def _run(name: str) -> tuple[dict, str, str, str]:
    """跑全量管线（宏展开 + 完整阶段），返回 (result, source, output, log)。"""
    with open(os.path.join(_REF_DIR, name), encoding="utf-8") as f:
        source = f.read()
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        result = run_pipeline_on_source(
            source=source, quiet=True, expand_macros=True, no_lint=True
        )
    log = out_buf.getvalue() + err_buf.getvalue()
    return result, source, result.get("output", ""), log


def _strip_all(text: str) -> str:
    """移除行注释与全部空白（与 test_real_fidelity._strip_all 一致）。"""
    lines = []
    for line in text.splitlines():
        ci = line.find("//")
        if ci >= 0:
            line = line[:ci]
        lines.append(line)
    return "".join("".join(lines).split())


@pytest.mark.parametrize("name", _MACRO_CASES)
def test_macro_case_succeeds_no_residual(name):
    """所有 macro 样本：管线成功、无 token/marker 残留。"""
    result, _, out, _ = _run(name)
    assert result["success"], f"{name}: {result.get('error', 'pipeline failed')}"
    assert "tpc:" not in out, f"{name}: 有 token/marker 残留"


@pytest.mark.parametrize("name", _FIDELITY_CASES)
def test_macro_roundtrip_fidelity(name):
    """简单样本 token 级保真度不低于阈值（内容丢失不可）。"""
    _, src, out, _ = _run(name)
    ratio = difflib.SequenceMatcher(None, _strip_all(src), _strip_all(out)).ratio()
    assert ratio >= _FIDELITY_THRESHOLD, f"{name} 保真度 {ratio:.3f} < {_FIDELITY_THRESHOLD}"


# ── 特定宏还原断言 ──────────────────────────────────────────


def test_func_macro_basic_reversed():
    """function-like 宏调用还原：assign z = `MIN(x, y);"""
    _, _, out, _ = _run("ref_pp_func_macro_basic.v")
    assert "`MIN(x, y)" in out


def test_func_macro_reverse_reversed():
    """function-like 宏调用还原：assign z = `MAX(x, y);"""
    _, _, out, _ = _run("ref_pp_func_macro_reverse.v")
    assert "`MAX(x, y)" in out


def test_func_macro_stmt_reversed():
    """function-like 宏作为语句体还原：`debug(reg_pc <= next_pc);"""
    _, _, out, _ = _run("ref_pp_func_macro_stmt.v")
    assert "`debug(reg_pc <= next_pc)" in out


def test_object_macro_sync_reversed():
    """object-like 宏多实例还原（同步词不串位）：`W / `BW 均保留。"""
    _, _, out, _ = _run("ref_macro_sync.v")
    assert "`W - 1:0" in out
    assert "`BW - 1:0" in out
    # 位宽字面量组合：`W'd0 / `BW'd0 整体还原（宏调用 + `'` 后缀），assign 行不丢
    # （formatter assignment 对齐在 assign 后可能加空格，只断言宏+后缀整体）
    assert "sig_a = `W'd0" in out
    assert "sig_b = `BW'd0" in out


def test_object_macro_def_reversed():
    """object-like 宏 + include：`WIDTH 还原保留。"""
    _, _, out, _ = _run("ref_macro_def.v")
    assert "`WIDTH" in out
    assert "`include" in out


def test_macro_complex_nested_reversed():
    """嵌套宏 + 位宽字面量组合（`W'd`RST）：整体还原为单链 fragment，不粘连。"""
    _, _, out, _ = _run("ref_macro_complex.v")
    assert "head <= `W'd`RST;" in out
    assert "tail <= `W'd`RST;" in out
    assert "tail <= tail + `W'd1;" in out


def test_ifdef_roundtrip_reversed():
    """条件块占位还原：`ifdef/`else/`endif 结构保留。"""
    _, _, out, _ = _run("ref_pp_ifdef_roundtrip.v")
    assert "`ifdef FEATURE" in out
    assert "`endif" in out


def test_empty_body_macro_inline_reversed():
    """空 body 宏行内占位（`TV80DELAY 1'b1）→ inline 注释锚，展开可解析 + 还原原样。

    空 body 宏 token 替换会留下 `tpc_marker_N 1'b1` 相邻原子（id + 位宽字面量）
    不可解析；inline 锚（`/*<marker>*/`）是 trivia，parser 跳过，还原原位回插
    宏调用。tv80 的 `define TV80DELAY（无替换体）在 `<=` 后行内使用即此形态。
    """
    src = (
        "`define TV80DELAY\n"
        "module m;\n"
        "    always @(posedge clk) begin\n"
        "        if (!rst_n)\n"
        "            rd_n <= `TV80DELAY 1'b1;\n"
        "    end\n"
        "endmodule\n"
    )
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        result = run_pipeline_on_source(
            source=src, quiet=True, expand_macros=True
        )
    assert result["success"], f"管线应成功: {result['error']}"
    out = result["output"]
    # 还原后宏调用保留（inline 注释回注位置可能有额外空格，核心段断言）
    assert "`TV80DELAY 1'b1;" in out, "空 body 宏应原位还原"
    assert "tpc_marker" not in out, "不应残留 marker"


def test_inline_comment_no_drift_with_macros():
    """展开路径普通行尾注释不漂移（only_tpc：宏 marker 回插，普通注释跳过）。

    宏展开改变行数 → 渲染行号与源行号错位，restore_comments 的 ±3 窗口会
    在错误区域匹配通用锚点（如 `end`）把注释错插到端口/参数行（tv80 的
    `end // case: x` 曾漂移到 `parameter Flag_H = 4;` 行尾）。修复后普通
    注释不参与展开路径回插，宏 marker 仍正常。
    """
    src = (
        "`define FLAG 1\n"
        "module m;\n"
        "    parameter Flag_H = 4;\n"
        "    always @(posedge clk) begin\n"
        "        if (rst_n)\n"
        "            q <= `FLAG;\n"
        "        else begin\n"
        "            case (x)\n"
        "                1: q <= 0;\n"
        "                default: ;\n"
        "            endcase\n"
        "        end // case: done\n"
        "    end\n"
        "endmodule // T80_ALU\n"
    )
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        result = run_pipeline_on_source(
            source=src, quiet=True, expand_macros=True
        )
    assert result["success"], f"管线应成功: {result['error']}"
    out = result["output"]
    # 普通注释不回插（漂移会污染声明行），宏正常还原
    assert "`FLAG" in out, "宏应还原"
    assert "tpc_marker" not in out, "不应残留 marker"
    for line in out.split("\n"):
        if line.strip().startswith("parameter") and "//" in line:
            raise AssertionError(f"普通注释漂移到参数行: {line!r}")


