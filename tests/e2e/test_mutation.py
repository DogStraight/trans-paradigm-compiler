"""test_mutation.py — 变异注入器门禁（检查能力：错误注入必然检出）。

断言（详见 eval_mutation.evaluate）：
- 基座洁净：每个正确基座零诊断（注入有效的前提）
- recall：每个注入器的目标检查必然检出（12 个错误类型全覆盖）
- FP：注入后诊断 ⊆ {目标} ∪ allowed_extra（注入只引入目标错误，
  不引发其他检查误报）
- 解析：变异不破坏语法（注入失败 ≠ 漏检，直接断言）

用法与统计口径同 eval_mutation.py；本文件是 pytest 门禁。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from analyzer.checker import ProjectChecker
from tests.e2e.eval_mutation import evaluate


def _gate(checker) -> dict:
    rows, summary = evaluate(checker)
    assert summary["base_dirty"] == 0, f"基座不干净: {summary['base_dirty']}"
    assert summary["recall_miss"] == 0, f"目标检查漏检: {summary['recall_miss']}"
    assert summary["extra_fp"] == 0, f"注入后多余诊断: {summary['extra_fp']}"
    assert summary["parse_fail"] == 0, f"变异破坏语法: {summary['parse_fail']}"
    assert summary["total"] > 0
    # 逐目标 recall 100%
    for code, v in summary["per_target"].items():
        assert v["hit"] == v["total"], (
            f"目标 {code} recall {v['hit']}/{v['total']} 非 100%"
        )
    return summary


def test_mutation_gate():
    checker = ProjectChecker(rules_dir="grammar/verilog")
    summary = _gate(checker)
    assert summary["recall_hit"] == summary["total"]
