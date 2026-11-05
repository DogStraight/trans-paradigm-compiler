"""对标基线门禁 —— tpc 与 verilator 的共识数不得无声下降。

动机（块 11 收口）：块 10 修好对拍口径后 verilator 共识 0 → 53，但此前只有人工
报告、没有版本库基线——对拍能力退化（解析失败、码族映射失配、oracle 调用坏掉）只能
靠人偶然发现。本门禁用 `tests/e2e/samples/real/benchmark_baseline.json` 的**共识下限**
把这条能力卡住。

口径（三条，刻意）：
- **只锚共识下限**：共识 = 双方同报且近似同行，与语料规模基本解耦；只许增不许降。
- **不锚「仅 tpc / 仅 oracle」**：这两个计数对语料规模与 oracle 版本敏感，锚死会假红；
  基线里只作上下文记录。
- **tpc 解析失败必须为 0**：任一工程解析不完整，共识数就失去判读意义。

oracle 缺席即 skip（CI 无 MSYS2/verilator 时不得假红）；基线缺失/字段不全则失败
（防门禁静默通过的真绿）。

复测/刷新基线：`python tests/e2e/eval_benchmark.py --oracle=verilator`（本机约 46s），
确认数字变化属于改进后改 `consensus_floor` 并说明原因。
"""

import importlib
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

_BASELINE = os.path.join("tests", "e2e", "samples", "real", "benchmark_baseline.json")


def _load_baseline() -> dict:
    with open(_BASELINE, encoding="utf-8") as f:
        return json.load(f)


def _verilator_ready() -> bool:
    """MSYS2 bash + verilator 都可执行才跑（否则 skip，不假红）。"""
    from tests.e2e import eval_benchmark as eb

    if not os.path.exists(eb._BASH):
        return False
    try:
        proc = subprocess.run(
            [eb._BASH, "-c",
             "export PATH=/mingw64/bin:/usr/bin:$PATH; verilator --version"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and "Verilator" in (proc.stdout + proc.stderr)


@pytest.fixture(scope="module")
def verilator_summary() -> dict:
    """真实语料跑一遍 verilator 对拍（7 工程，本机约 46s；并行争抢上限见 mark）。"""
    if not _verilator_ready():
        pytest.skip("verilator 不可用（MSYS2/verilator 缺失）：CI 无 oracle 时跳过，不算失败")
    from tests.e2e import eval_benchmark as eb

    checker = eb.ProjectChecker(rules_dir="grammar/verilog")
    groups = [
        {
            **g,
            "files": [os.path.join(eb._REAL_DIR, f) for f in g["files"]],
            "entry": os.path.join(eb._REAL_DIR, g["files"][0]),
        }
        for g in eb._GROUPS
    ]
    _, summary = eb.run(checker, groups, "real", oracles=["verilator"])
    return summary


def test_baseline_is_well_formed() -> None:
    """基线字段齐全且下限为正——防手改成空基线导致门禁恒绿。"""
    data = _load_baseline()
    assert data.get("oracle") == "verilator", f"oracle 字段应为 verilator：{data.get('oracle')!r}"
    floor = data.get("consensus_floor")
    assert isinstance(floor, int) and floor > 0, f"consensus_floor 必须为正整数：{floor!r}"
    context = data.get("context") or {}
    assert context.get("consensus", 0) >= floor, (
        "context.consensus 应不低于 consensus_floor（上下限自相矛盾）"
    )


@pytest.mark.timeout(600)  # 并行争抢下 46s → 最长约 2.5x，放宽默认 120s 上限
def test_consensus_not_below_floor(verilator_summary) -> None:
    """共识数不得低于基线下限（只许增不许降）。"""
    floor = _load_baseline()["consensus_floor"]
    actual = verilator_summary["per_oracle"]["verilator"]["consensus"]
    assert actual >= floor, (
        f"verilator 共识 {actual} < 基线下限 {floor}——对拍能力退化"
        "（解析失败 / 码族映射失配 / oracle 调用坏掉）。先看 "
        "`python tests/e2e/eval_benchmark.py --oracle=verilator` 的明细；"
        "若属真改进后的口径/语料变更，核准后改 baseline.json 的 consensus_floor 并说明原因。"
    )


@pytest.mark.timeout(600)
def test_no_tpc_parse_fail(verilator_summary) -> None:
    """任一工程 tpc 解析不完整 ⇒ 共识数失去判读意义，直接红。"""
    fails = verilator_summary["tpc_parse_fail"]
    assert fails == 0, (
        f"{fails} 个真实工程 tpc 解析失败，对拍结论不可信；"
        "先修解析（`python tests/e2e/eval_benchmark.py --oracle=verilator` 看 TPC-PARSE-FAIL 行）"
    )
