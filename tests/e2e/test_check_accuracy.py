"""tests/e2e/test_check_accuracy.py — analyzer 规则检出准确度门禁（0.1.1 试水）。

对 tests/e2e/samples/check_accuracy/ 下全部标注样本（56 case：35 正样例 +
21 负样例，覆盖 UN001 / W101-W106 / WC001 / W201-W202 / CC001 / LC001 /
AW001-AW002 / NC012-NC013 / TP 族）跑 ProjectChecker，断言：

    recall = 100%   — 正样例期望规则码全部检出（漏检 = MISS）
    FP = 0          — 负样例零误报 + 正样例无期望外规则码
    parse_err = 0   — 样本全部可解析（语义阶段不被跳过）

判定逻辑与 tests/e2e/eval_check_accuracy.py 的 evaluate() 单一来源
（--json 打印与 pytest 断言共享同一实现）。试水期基线：18 期望码全命中
（2026-08-29 首测 80%→修复 W105 信号图 assign 驱动 + TypeSpecNoReg tri
缺口后达 100%）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport]

from analyzer.checker import ProjectChecker  # noqa: E402
from tests.e2e.eval_check_accuracy import evaluate  # noqa: E402


def _run() -> tuple[list[dict], dict]:
    checker = ProjectChecker(rules_dir="grammar/verilog")
    return evaluate(checker)


def test_recall_100_percent():
    """正样例期望规则码全部检出（无漏检）。"""
    rows, summary = _run()
    assert summary["miss"] == 0, (
        f"漏检 {summary['miss']} 个期望码："
        + "; ".join(
            f"{r['case']} 缺 {r['missed']}" for r in rows if r["missed"]
        )
    )
    assert summary["hit"] == summary["expect_codes"]


def test_zero_false_positive():
    """负样例零误报 + 正样例无期望外规则码。"""
    rows, summary = _run()
    assert summary["fp"] == 0, (
        f"误报 {summary['fp']} 个规则码："
        + "; ".join(
            f"{r['case']} 多出 {r['extra']}" for r in rows if r["extra"]
        )
    )


def test_all_samples_parse():
    """全部样本可解析（语义阶段不被语法错误跳过）。"""
    rows, summary = _run()
    assert summary["parse_err"] == 0, (
        "解析失败样本："
        + "; ".join(r["case"] for r in rows if r["parse_fail"])
    )
