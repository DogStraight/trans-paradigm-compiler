"""真实语料诊断计数基线门禁 —— 误报面不得无声增长。

动机：规则的默认开/关是"数据决策"（AGENTS 纪律），但真实语料上的误报面
此前只有人工量化、无留存记录 → 规则改动引发的误报增长只能靠人偶然发现。
本门禁把 `tests/e2e/samples/real/diag_baseline.json` 的计数卡住：**只许减
不许增**——减少（修好了）自动放行，增加则失败并要求解释。

两向设计：
- 增加即失败：给出码级增量，迫使"要么修、要么显式更新基线并说明原因"。
- 减少不失败但提示：避免"修好了反而红"；同时提示可刷新基线，让基线不腐。
- 基线自洽校验：`total` 必须等于 `counts` 之和，防手改后两处不一致。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport]


@pytest.fixture(scope="module")
def comparison() -> tuple[dict, dict, dict]:
    """跑一遍真实语料并返回 (增长, 减少, 持平)。"""
    from tests.e2e.eval_diag_baseline import collect, compare, load_baseline

    current = collect()
    baseline = load_baseline().get("counts", {})
    return compare(current, baseline)


def test_no_diagnostic_growth(comparison) -> None:
    """诊断条数不得增加（修好导致的减少放行）。"""
    grew, _, _ = comparison
    assert not grew, (
        "真实语料上的诊断条数增加——需解释是修复带来的真诊断还是误报回归；"
        "确需更新基线时跑 `python tests/e2e/eval_diag_baseline.py --update` "
        "并说明原因：\n  "
        + "\n  ".join(f"{c}: {was} → {now} (+{now - was})" for c, (was, now) in grew.items())
    )


def test_baseline_is_self_consistent() -> None:
    """基线 `total` 必须等于 `counts` 之和（防手改后两处漂移）。"""
    from tests.e2e.eval_diag_baseline import load_baseline

    data = load_baseline()
    counts = data.get("counts", {})
    assert data.get("total") == sum(counts.values()), (
        f"基线 total={data.get('total')} 与 counts 之和 {sum(counts.values())} 不一致"
    )


def test_baseline_nonempty() -> None:
    """基线非空——防清空后门禁静默通过（假绿）。"""
    from tests.e2e.eval_diag_baseline import load_baseline

    counts = load_baseline().get("counts", {})
    assert counts, "基线为空：门禁会静默通过，请先 --update 生成"
