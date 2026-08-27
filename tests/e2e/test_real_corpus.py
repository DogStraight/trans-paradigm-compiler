"""tests/e2e/test_real_corpus.py — 真实语料回归基线（real corpus regression）。

真实开源 Verilog 文件（tests/e2e/samples/real/ref/，归属/许可见同目录
CREDITS.md）的全管线回归守卫：parse + format + lint + 幂等 + 保真 + sv-parser
差分门禁。

语料（2026-08-27 扩至 9 文件）：
- 4 个 CPU 核：darkriscv（BSD-3）/ picorv32（ISC）/ serv_top（ISC）/ tv80（MIT）
- UART×3：alexforencich/verilog-uart（MIT，无宏，可差分）
- simcells：yosys techlibs（ISC），149 个 UDP/门级仿真单元
- ice40_cells_sim：yosys techlibs（ISC），specify 时序块 + 多目标 assign +
  `===` + 模块头属性；需预定义 NO_ICE40_DEFAULT_ASSIGNMENTS（文件自带的
  Verilog-2005 兼容开关，见 CREDITS.md）

特性覆盖画像：specify（ice40）、UDP/门级原语（simcells/darkriscv/tv80）、
多目标 assign / `===`（ice40，test_2005_batch7 修复）、模块头属性（ice40）、
条件编译宏（darkriscv/picorv32/ice40）、系统任务 $display/$finish
（darkriscv/picorv32/simcells）。

每文件断言：
- 全量管线 success + lint 零诊断 + 无占位符残留
- 幂等（展开路径由 run_pipeline 内建判定，见 test_real_fidelity）
- 结构完整：module 数 ≥ manifest 下限（防静默截断——picorv32 曾只出 1 个 module）
- token 级保真度 ≥ 0.80（格式化差异可容忍，内容丢失不可）

差分门禁（仅无宏文件）：sv-parser（IEEE 1800-2017）接受 ∧ tpc 必须接受
（假拒检测）；tpc 输出必须被 sv-parser 接受（互操作）。二进制缺失自动跳过
（与 tests/differential/run_differential_svparser.py 同机制）。
"""

import difflib
import io
import contextlib
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport]

from tests.e2e.run_pipeline import run_pipeline_on_source  # noqa: E402

_REAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "real")
_REF_DIR = os.path.join(_REAL_DIR, "ref")

# ── 语料清单：文件 → (特性标签, module 数下限, 预定义宏) ────────────────
# 新文件加入 real/ref/ 时在此登记；无法全绿的语料暂不入库（见 CREDITS.md
# "语料边界注"，如 yosys techmap 的 $cell 内部名）。
_MANIFEST: dict[str, tuple[list[str], int, dict[str, str]]] = {
    "ref_darkriscv.v": (["宏", "门级", "UDP", "系统任务"], 1, {}),
    "ref_ice40_cells_sim.v": (["specify", "多目标assign", "===", "模块属性", "宏"], 50, {"NO_ICE40_DEFAULT_ASSIGNMENTS": "1"}),
    "ref_picorv32.v": (["宏", "生成", "任务"], 8, {}),
    "ref_serv_top.v": (["生成"], 1, {}),
    "ref_simcells.v": (["UDP", "门级", "系统任务"], 149, {}),
    "ref_tv80_core.v": (["门级", "任务"], 5, {}),
    "ref_uart.v": (["实例化", "参数"], 1, {}),
    "ref_uart_rx.v": (["实例化", "参数", "==="], 1, {}),
    "ref_uart_tx.v": (["实例化", "参数"], 1, {}),
}

_FIDELITY_THRESHOLD = 0.80

# sv-parser 二进制定位（与 run_differential_svparser.py 同机制）
_TOOLS_BIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "differential", ".tools", "sv-parser", "parse_sv.exe",
)
SV_PARSER = (
    os.environ.get("SV_PARSER")
    or (_TOOLS_BIN if os.path.isfile(_TOOLS_BIN) else None)
)


def _strip_all(text: str) -> str:
    """移除行注释与全部空白（与 run_all_tests._strip_all 一致）。"""
    lines = []
    for line in text.splitlines():
        ci = line.find("//")
        if ci >= 0:
            line = line[:ci]
        lines.append(line)
    return "".join("".join(lines).split())


def _has_macro(source: str) -> bool:
    return any(m in source for m in ("`ifdef", "`define", "`include"))


def _run_file(name: str, predefined: dict[str, str]):
    """跑全量管线（宏展开 + lint + 渲染），返回 (result, source, output, log)。"""
    with open(os.path.join(_REF_DIR, name), encoding="utf-8") as f:
        source = f.read()
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        result = run_pipeline_on_source(
            source=source,
            quiet=True,
            expand_macros=True,
            no_lint=False,
            predefined=predefined or None,
        )
    log = out_buf.getvalue() + err_buf.getvalue()
    return result, source, result.get("output", ""), log


@pytest.mark.parametrize("name", sorted(_MANIFEST))
def test_file_parses_clean(name: str):
    """全量管线 success + lint 零诊断 + 无占位符残留 + 幂等。"""
    _, min_modules, predefined = _MANIFEST[name]
    result, source, output, log = _run_file(name, predefined)
    assert result["success"], (
        f"{name}: pipeline failed: {result.get('error', '')}\n{log[:2000]}"
    )
    assert "[linter]" not in log, f"{name}: lint 诊断残留:\n{log[:2000]}"
    assert output.count("<tpc:") == 0, f"{name}: 条件编译占位符残留"
    assert result.get("idempotent", False) is True, f"{name}: 非幂等"


@pytest.mark.parametrize("name", sorted(_MANIFEST))
def test_module_count_intact(name: str):
    """module 数不低于 manifest 下限（防静默截断/占位符吞模块）。"""
    _, min_modules, predefined = _MANIFEST[name]
    result, _, output, _ = _run_file(name, predefined)
    count = output.count("module ")
    assert count >= min_modules, (
        f"{name}: 产出 {count} 个 module，低于下限 {min_modules}"
    )


@pytest.mark.parametrize("name", sorted(_MANIFEST))
def test_fidelity_above_threshold(name: str):
    """token 级保真度不低于阈值（格式化差异可容忍，内容丢失不可）。"""
    _, min_modules, predefined = _MANIFEST[name]
    result, source, output, _ = _run_file(name, predefined)
    ref_flat = _strip_all(source)
    out_flat = _strip_all(output)
    ratio = difflib.SequenceMatcher(None, ref_flat, out_flat).ratio()
    assert ratio >= _FIDELITY_THRESHOLD, (
        f"{name}: 保真度 {ratio:.4f} < {_FIDELITY_THRESHOLD}"
    )


def _sv_parser_accepts(path: str) -> bool:
    assert SV_PARSER is not None  # skipif 守卫缺失二进制
    r = subprocess.run([SV_PARSER, "-q", path], capture_output=True, timeout=120)
    return r.returncode == 0


@pytest.mark.skipif(SV_PARSER is None, reason="parse_sv 二进制未找到（tests/differential/.tools/sv-parser/）")
@pytest.mark.parametrize("name", sorted(_MANIFEST))
def test_svparser_accept_domain_and_interop(name: str):
    """sv-parser 差分门禁（仅无宏文件）：假拒检测 + 互操作。

    sv-parser 是 IEEE 1800-2017 全量；无宏的 2005 语料被 sv-parser 接受时，
    tpc 必须接受（假拒 = 真缺陷）；tpc 渲染输出必须被 sv-parser 接受。
    宏文件两边预处理器语义不同，不构成对拍样本（同 run_differential_svparser）。
    """
    _, min_modules, predefined = _MANIFEST[name]
    with open(os.path.join(_REF_DIR, name), encoding="utf-8") as f:
        source = f.read()
    if _has_macro(source):
        pytest.skip(f"{name}: 含宏指令，不构成对拍样本")

    assert _sv_parser_accepts(os.path.join(_REF_DIR, name)), (
        f"{name}: sv-parser 拒收（语料问题，非 tpc 缺陷——先核对语料）"
    )

    result, _, output, _ = _run_file(name, predefined)
    assert result["success"], f"{name}: tpc 管线失败（假拒嫌疑）"
    tmp = os.path.join(_REF_DIR, name + ".tpc_out.v")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(output)
        assert _sv_parser_accepts(tmp), (
            f"{name}: tpc 渲染输出不被 sv-parser 接受（互操作失败）"
        )
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)


def test_manifest_feature_coverage():
    """manifest 特性标签覆盖真实语料的特征面（文档守卫）。"""
    all_tags = {t for tags, _, _ in _MANIFEST.values() for t in tags}
    for expect in ("specify", "UDP", "===", "多目标assign", "模块属性", "宏", "门级"):
        assert expect in all_tags, f"manifest 缺少特性标签 {expect!r}"
