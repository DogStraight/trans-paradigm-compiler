"""C 真实语料诊断计数基线门禁 —— 误报面不得无声增长（退出判据 5）。

Doc: docs/gaps/gap-c-real-corpus.md（门禁方案 A/判据 1–7）、tests/e2e/eval_diag_baseline_c.py

语料 = `tests/e2e/samples/real_c_ref/`（cJSON 1.7.19 + zlib 1.3.2 核心文件；
归属/许可见 CREDITS.md）。口径与 verilog 先例同构：**只许减不许增**。

两向设计：
- 增长即失败：给出码级增量，迫使"要么修、要么显式 --update 并说明原因"；
- 减少不失败但提示刷新（避免基线腐化）；
- 非空/非假绿：语料清单必须齐全 + **每文件解析完整**（`parse_ok`，结构层截断会置
  False；这是 #43 报告更正后的口径）+ 基线 `total` 自洽 + collect 确定性。
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）


@pytest.fixture(scope="module")
def report() -> dict:
    from tests.e2e.eval_diag_baseline_c import collect_report

    return collect_report()


def test_corpus_manifest_complete(report) -> None:
    """语料清单齐全（防语料缺失导致门禁空转）。"""
    from tests.e2e.eval_diag_baseline_c import _MANIFEST

    names = [f["name"] for f in report["files"]]
    assert names == list(_MANIFEST), names


def test_parse_complete(report) -> None:
    """每文件解析完整（截断 ⇒ parse_ok False ⇒ 门禁失败，不许固化部分 AST）。"""
    bad = [f for f in report["files"] if not f["parse_ok"] or f["parse_error"]]
    assert not bad, bad


def test_no_diagnostic_growth(report) -> None:
    """诊断条数不得增加（修好导致的减少放行）。"""
    from tests.e2e.eval_diag_baseline_c import compare, load_baseline

    baseline = load_baseline().get("counts", {})
    grew, _, _ = compare(report["counts"], baseline)
    assert not grew, (
        "C 真实语料诊断条数增加——需解释是修复带来的真诊断还是误报回归；"
        "确需更新基线时跑 `python tests/e2e/eval_diag_baseline_c.py --update` "
        "并说明原因：\n  "
        + "\n  ".join(
            f"{c}: {was} → {now} (+{now - was})" for c, (was, now) in grew.items()
        )
    )


def test_baseline_is_self_consistent() -> None:
    from tests.e2e.eval_diag_baseline_c import load_baseline

    data = load_baseline()
    counts = data.get("counts", {})
    assert data.get("total") == sum(counts.values()), (
        f"基线 total={data.get('total')} 与 counts 之和 {sum(counts.values())} 不一致"
    )


# 注：判据 5 的"采集确定性"未单列测试——collect() 为确定性纯函数（`dict(sorted(...))`），
# 且单次采集 ≈120s（cJSON 解析回溯成本，见 TODO 性能项），二次采集会让门禁变慢一倍；
# 采集结果只含 code→int，无集合序暴露面。
