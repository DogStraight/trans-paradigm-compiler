"""linter 错误发现准确度回归门禁。

复用 tests/e2e/eval_lint_accuracy.evaluate() 的单一判定逻辑，把准确度
对照实验固化为 pytest 断言——错误样本必须全检出且类别命中期望，合法
样本必须零误报。任何未来改动把 recall/类别准确率/精确率拉低都会在此
失败，防止"测试不敏感、回归悄悄发生"（审计教训）。

样本集：verilog/tests/lint_err/ref/*.v + expected.json
"""

import os
import sys

import pytest

# 项目根（conftest 已加入，此处幂等兜底；文件位于 tests/engine/linter/，向上四层）
_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.define import DEFAULT_RULES_DIR
from linter.scanner import LinterScanner
from tests.e2e.eval_lint_accuracy import evaluate

# known_miss（已知漏检登记）的硬上限：防止把新漏检悄悄标成 known_miss
# 来维持门禁绿色（虚假绿风险）。超过上限说明测试在靠豁免掩盖漏检。
MAX_KNOWN_MISS = 3


@pytest.fixture(scope="module")
def accuracy() -> tuple[list[dict], dict]:
    """跑一遍完整准确度实验，返回 (rows, summary)。"""
    scanner = LinterScanner(DEFAULT_RULES_DIR)
    return evaluate(scanner)


def test_error_sample_set_is_nonempty(accuracy) -> None:
    """样本集非空，防止样本清空后测试假绿。"""
    _, summary = accuracy
    assert summary["err_total"] >= 10
    assert summary["valid_total"] >= 3


def test_error_samples_all_detected(accuracy) -> None:
    """错误样本全部检出（>=1 诊断）→ 无未知漏检。

    known_miss 样本（expected.json 显式标记）不计入——它们被门禁单独
    追踪（test_known_miss_tracked），修复后自动转 HIT。
    """
    rows, summary = accuracy
    miss = [r["file"] for r in rows if r["verdict"] == "MISS"]
    assert summary["miss"] == 0, f"漏检样本: {miss}"


def test_known_miss_tracked(accuracy) -> None:
    """known_miss 样本被显式追踪（KNOWN-MISS 判定），且有硬上限防滥用。

    known_miss 是"已知漏检"的显式登记（expected.json 标记）；修复后清空。
    当前 0 表示无已知漏检——之前 e15 在此登记，本次修复后转 HIT。
    """
    rows, summary = accuracy
    known = [r["file"] for r in rows if r["verdict"] == "KNOWN-MISS"]
    assert summary["known_miss"] == len(known)
    # 防滥用（虚假绿）：known_miss 必须有限度；超过上限说明门禁在靠豁免
    # 维持绿色，应修复漏检而非登记豁免。
    assert summary["known_miss"] <= MAX_KNOWN_MISS, (
        f"known_miss {summary['known_miss']} 超过上限 {MAX_KNOWN_MISS}，"
        "请修复这些漏检而不是登记豁免（否则门禁是虚假绿）"
    )


def test_error_category_always_hit(accuracy) -> None:
    """检出样本类别全部命中期望 → 类别准确率 100%。"""
    rows, summary = accuracy
    bad = [r["file"] for r in rows if r["verdict"] == "DETECTED-BADCODE"]
    assert summary["detected_badcode"] == 0, f"检出但类别不符: {bad}"


def test_no_false_positive(accuracy) -> None:
    """合法样本零误报 → FP=0 / 精确率 100%。"""
    rows, summary = accuracy
    fp = [r["file"] for r in rows if r["verdict"] == "FP"]
    assert summary["fp"] == 0, f"误报样本: {fp}"


def test_valid_samples_all_clear(accuracy) -> None:
    """合法样本逐条确认 verdict 为 OK（不依赖 summary 计数）。"""
    rows, _ = accuracy
    fp = [r["file"] for r in rows if not r["external"] and r["expect"] == [] and r["verdict"] != "OK"]
    assert fp == [], f"合法样本出现诊断: {fp}"


def test_normal_samples_no_diagnostic() -> None:
    """normal/ref 全部合法样本零诊断（零误报回归保护，含 28 个真实样例）。"""
    normal_dir = os.path.join(_ROOT, "tests", "e2e", "samples", "normal", "ref")
    files = sorted(f for f in os.listdir(normal_dir) if f.endswith(".v"))
    assert files, "normal/ref 样本为空"
    scanner = LinterScanner(DEFAULT_RULES_DIR)
    flagged = []
    for fname in files:
        with open(os.path.join(normal_dir, fname), encoding="utf-8") as f:
            src = f.read()
        errs = scanner.scan(src)
        if errs:
            flagged.append((fname, [(e.code, e.message[:50]) for e in errs]))
    assert flagged == [], f"normal 样本出现诊断: {flagged}"
