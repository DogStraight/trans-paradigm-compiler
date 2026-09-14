"""文档数字漂移门禁 —— 声明样本规模/覆盖面的地方不得写死数字。

动机：同一事实多处陈述必然漂移。0.1.2 收尾轮里 case 数/期望码数在
docstring、CHANGELOG、TODO 各写一遍，**同一轮错了三次**，全靠实测输出
才发现。解法不是"下次记得同步"，而是消灭复述点：数字由
`tests/e2e/eval_check_accuracy.sample_stats()` 从 `expected.json` 现算，
文档只引用来源或改述。

设计取舍（两条，都是刻意的）：
- **不扫全仓库**：CHANGELOG 历史条目、references 调研记录里的数字是历史
  陈述（当时为真），纳入扫描只会制造噪声并诱使大家加豁免——而豁免通路
  一旦打开，门禁就退化成"大家同意忽略它"。故只纳管 `_TARGETS` 清单；
  清单**故意手工维护**：纳管范围是"需要保持准确"这一判断的结果，不是
  文件类型的机械集合。
- **跳过 `>` 引用块**：按文档纪律，引用块是"指明待办方向的上下文"，
  不应沉淀规模数字；故只校验正文行（引用块靠"不写数字"约定，本次已清）。

自检：正则失效是这类门禁最可能的假绿形态（扫了但一条也匹配不上），
故 `test_patterns_match_known_samples` 用典型样本串反证模式仍然有效。
"""

import importlib
import os
import re
import sys

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

# 纳管清单（相对仓库根）。新增"声明规模数字"的文件时显式加入。
_TARGETS = [
    "tests/e2e/test_check_accuracy.py",
    "TODO.md",
]

# 禁用模式 → 该数字是什么（诊断信息用）。只覆盖"能自动算的当前事实"。
# _NUM 的负向后顾很关键：规则码本身含数字（"CC001 case 无 default"），
# 不加会被当成规模数字误报——门禁的误报比漏报更伤（诱发无谓的文档改写）。
_NUM = r"(?<![A-Za-z0-9])\d+"
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(_NUM + r"\s*case"), "case 总数"),
    (re.compile(_NUM + r"\s*正样例"), "正样例数"),
    (re.compile(_NUM + r"\s*负样例"), "负样例数"),
    (re.compile(r"focus\s*" + _NUM + r"\s*码"), "focus 码数"),
    (re.compile(_NUM + r"\s*个已定义码"), "已定义码数"),
    (re.compile(_NUM + r"\s*期望码"), "期望码数"),
]


def _violations() -> list[str]:
    """清单文件正文行里写死的规模数字（跳过 `>` 引用块）。"""
    found: list[str] = []
    for rel in _TARGETS:
        with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if line.lstrip().startswith(">"):
                    continue  # 引用块 = 背景上下文，不纳管（见模块 docstring）
                for pattern, label in _PATTERNS:
                    if pattern.search(line):
                        found.append(
                            f"{rel}:{lineno} 写死了{label}：{line.strip()[:70]}"
                        )
    return found


def test_no_hardcoded_sample_stats() -> None:
    """正文不得写死规模数字——改用 sample_stats() / eval 输出引用。"""
    violations = _violations()
    assert not violations, (
        "以下位置写死了会自动漂移的规模数字，请改为引用单一来源"
        "（`sample_stats()` 或 eval 输出）或改述为定性描述：\n  "
        + "\n  ".join(violations)
    )


def test_targets_exist() -> None:
    """清单文件必须存在——路径写错会让扫描静默空转（假绿）。"""
    missing = [r for r in _TARGETS if not os.path.isfile(os.path.join(_ROOT, r))]
    assert not missing, f"纳管清单里这些文件不存在（路径写错？）：{missing}"


def test_patterns_match_known_samples() -> None:
    """正则自身自检：典型违规串必须仍被命中（防模式失效后假绿）。"""
    samples = [
        "（69 case：45 正样例 + 24 负样例",
        "focus 37 码 @ 67 case",
        "共 39 个已定义码",
        "recall 100%（51 期望码全命中）",
        "linter 强检 33 正样例 / 7 负样例",
    ]
    for text in samples:
        assert any(p.search(text) for p, _ in _PATTERNS), (
            f"自检失败：{text!r} 未被任何模式命中——模式已失效"
        )


def test_patterns_ignore_code_tokens() -> None:
    """反向自检：规则码自带数字的表述不得被误判为规模数字。

    这是首版真实发生的误报——`CC001 case 无 default` 被当成"case 总数"。
    门禁的误报代价高于漏报：它会诱发无谓的文档改写，进而让人想加豁免。
    """
    non_violations = [
        "- [x] ~~分支完整性：CC001 case 无 default~~（已完成）",
        "W201 case 分支 / W105 多驱动（跨模块）",
        "phase-statement / phase1-boundary（K 类码）",
    ]
    for text in non_violations:
        hits = [label for p, label in _PATTERNS if p.search(text)]
        assert not hits, f"误报：{text!r} 被判为 {hits}"


def test_sample_stats_matches_evaluation() -> None:
    """单一来源自身要正确：sample_stats() 与实跑评测的统计必须一致。

    focus 码数不比（评测 summary 不暴露该键；样本码集合的正确性由
    `test_rule_coverage.py` 的反向核验覆盖）。
    """
    from analyzer.checker import ProjectChecker
    from tests.e2e.eval_check_accuracy import evaluate, sample_stats

    stats = sample_stats()
    _, summary = evaluate(ProjectChecker(rules_dir="grammar/verilog"))
    assert stats["pos"] == summary["pos_total"]
    assert stats["neg"] == summary["neg_total"]
    assert stats["expect_codes"] == summary["expect_codes"]
