"""PicoRV32 真实项目保真度测试（real 组回归守卫）。

背景：全量管线解析 PicoRV32 曾因"裸 `id ;` 任务调用"语法缺口在 L471 静默
软失败，丢弃 module 2-8（success=True 但只产出 1 个 module）。修复后全量
解析产出 8 个 module、post-lint 0、占位符 0。本测试把"生成效果"固化为断言，
防止后续改动导致保真度回退。

覆盖（管线真实效果）：
- 结构完整：8 个 module 全部产出、无占位符残留
- 幂等：生成代码可再次被管线稳定处理（第二遍 parse 无 truncated）
- 内容保真：关键语法构造保留（裸任务调用、字符串字面量、localparam 类型、
  嵌套条件块），token 级保真度不低于阈值
"""

import os
import re
import sys
import io
import contextlib
import difflib

import pytest

# 项目根加入 sys.path（必须在 import core 之前）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:  # noqa: E402
    sys.path.insert(0, _PROJECT_ROOT)  # noqa: E402

from tests.e2e.run_pipeline import run_pipeline_on_source  # noqa: E402

_REAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "real")
_REF_PATH = os.path.join(_REAL_DIR, "ref", "ref_picorv32.v")

# 保真度阈值：格式化差异（间隔/换行/间距规范化）会拉低 ratio，0.80 足够
# 区分"结构完整重排"与"内容丢失/模块截断"（后者通常 < 0.5）。
_FIDELITY_THRESHOLD = 0.80

_EXPECTED_MODULES = [
    "picorv32",
    "picorv32_regs",
    "picorv32_pcpi_mul",
    "picorv32_pcpi_fast_mul",
    "picorv32_pcpi_div",
    "picorv32_axi",
    "picorv32_axi_adapter",
    "picorv32_wb",
]


@pytest.fixture(scope="module")
def picorv32_result():
    """跑全量管线（宏展开 + 完整阶段），返回 (result, source, output, log)。"""
    with open(_REF_PATH, encoding="utf-8") as f:
        source = f.read()

    # 捕获管线 stdout/stderr（quiet=True 下主要是 stderr 的 WARN/failure-report）
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        result = run_pipeline_on_source(
            source=source,
            quiet=True,
            expand_macros=True,
            no_lint=False,
        )
    log = out_buf.getvalue() + err_buf.getvalue()
    return result, source, result.get("output", ""), log


def _strip_all(text: str) -> str:
    """移除行注释与全部空白（与 run_all_tests._strip_all 一致）。"""
    lines = []
    for line in text.splitlines():
        ci = line.find("//")
        if ci >= 0:
            line = line[:ci]
        lines.append(line)
    return "".join("".join(lines).split())


def test_full_pipeline_succeeds(picorv32_result):
    """管线整体成功，无错误。"""
    result, _, _, _ = picorv32_result
    assert result["success"], result.get("error", "pipeline failed")


def test_all_8_modules_rendered(picorv32_result):
    """8 个 module 全部产出（曾只产出 1 个）。"""
    _, _, out, _ = picorv32_result
    mods = re.findall(r"^module\s+(\w+)", out, re.M)
    assert len(mods) == len(_EXPECTED_MODULES), f"module 数 {len(mods)}: {mods}"
    assert mods == _EXPECTED_MODULES


def test_output_idempotent(picorv32_result):
    """生成代码可再次被管线稳定处理（第二遍 parse 无 truncated）。

    picorv32 走展开路径（条件编译），run_pipeline 对展开路径跳过幂等检查
    （内容变化是展开语义），idempotent 恒 True——本断言守卫展开路径不误报。
    非展开路径的真实幂等检查由 tests/e2e/test_idempotent.py 覆盖。
    """
    result, _, _, _ = picorv32_result
    assert result.get("idempotent", False) is True


def test_no_placeholder_residual(picorv32_result):
    """条件编译占位符全部恢复（曾残留 6 个嵌套 marker）。"""
    _, _, out, _ = picorv32_result
    assert out.count("<tpc:cond:") == 0


def test_parser_no_warnings(picorv32_result):
    """解析过程无匹配失败警告。"""
    _, _, _, log = picorv32_result
    assert "匹配失败" not in log
    assert "WARN" not in log


def test_fidelity_above_threshold(picorv32_result):
    """token 级保真度不低于阈值（格式化差异可容忍，内容丢失不可）。"""
    _, src, out, _ = picorv32_result
    ref_flat = _strip_all(src)
    out_flat = _strip_all(out)
    ratio = difflib.SequenceMatcher(None, ref_flat, out_flat).ratio()
    assert ratio >= _FIDELITY_THRESHOLD, f"保真度 {ratio:.4f} < {_FIDELITY_THRESHOLD}"


def test_key_constructs_preserved(picorv32_result):
    """关键语法构造在生成输出中完整保留。"""
    _, _, out, _ = picorv32_result
    # 裸任务调用（assert 宏展开为 empty_statement;）
    assert "empty_statement;" in out
    # 字符串字面量 RHS（曾静默丢弃 → `= ;`）
    assert 'new_ascii_instr = "";' in out
    assert 'if (instr_lui)' in out and 'new_ascii_instr = "lui";' in out
    # localparam 显式类型（曾丢 integer / [range]）；formatter 列对齐后 name
    # 列前可能有多空格，去空白匹配
    assert "localparamintegerirq_timer=0;" in _strip_all(out)
    # 位宽 localparam：formatter 对齐后 name 列前可能有多空格，去空白匹配
    assert "localparam[35:0]TRACE_BRANCH" in _strip_all(out)
    # 嵌套条件块完整恢复
    assert "`ifdef RISCV_FORMAL" in out
    assert "`ifdef PICORV32_TESTBUG_003" in out
    assert "`ifdef PICORV32_TESTBUG_004" in out


def test_no_cond_block_misplacement(picorv32_result):
    """条件块回插不错位：RISCV_FORMAL 端口块不应被回插到错误模块（pcpi_div/axi 之间）。

    曾因 restore_line_comments 用裸源行号窗口回插被吞的条件占位 marker，
    在模块边界（渲染行号与源行号偏移 ±150）错位，RISCV_FORMAL 端口声明被
    插到 picorv32_pcpi_div 与 picorv32_axi 之间并多出一个 `endif。
    """
    _, _, out, _ = picorv32_result
    div_m = re.search(r"^module\s+picorv32_pcpi_div\b", out, re.M)
    axi_m = re.search(r"^module\s+picorv32_axi\b", out, re.M)
    assert div_m is not None and axi_m is not None
    assert axi_m.start() > div_m.start()
    between = out[div_m.end() : axi_m.start()]
    assert "rvfi_valid" not in between, "RISCV_FORMAL 端口块被回插到 pcpi_div/axi 之间"


def test_directives_in_place(picorv32_result):
    """指令行原位还原：`timescale/`define 不再堆到文件头，分散在各自原位。

    曾因 directive_lines 头部拼接把所有指令行堆到输出开头；改为原位占位
    （marker 回插）后，指令行回到原始位置（版权注释之后、ifdef 块内等）。
    """
    _, _, out, _ = picorv32_result
    assert not out.lstrip().startswith("`timescale"), "指令行被堆到文件头"
    assert "`timescale 1 ns / 1 ps" in out
    assert "`define PICORV32_V" in out
    assert "`define assert(assert_expr) empty_statement" in out

