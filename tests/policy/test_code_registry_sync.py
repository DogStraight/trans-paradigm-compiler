"""诊断码登记点同步门禁（0.1.3 WS2 步 2）。

**问题**：一条规则码今天要被手写进 6 处（实测散点 5–6 个文件/码，见
`docs/gaps/gap-feature-scatter.md`）。其中**机器可读**的登记点若忘了同步，症状各异且
都**不响亮**：变异注入器指向已删码 → 该变异静默不生效；评测基准映射指向已删码 →
评分少算一类；真实语料基线留着已删码 → 基线与现实脱节。

**做法**：码的**单一来源** = 声明式规则表 ∪ 插件 handler `code=` 字面量
（`tests/_rule_codes.py`，与 `test_rule_coverage.py` 共用**同一份提取实现**）。
本门禁把机器可读登记点全部接上校验：**引用的码必须已定义**（反方向"已定义但没登记"
不在此断言——那是评测覆盖问题，属 `test_rule_coverage.py`）。

非机器可读的散文（`analyzer/semantic_checks.md` 等）**不在**本门禁范围：文档里的码
会成段/成范围出现（`NC001-NC010`），也会作为历史提及，逐 token 校验会产生误报；
文档侧由 `test_doc_stats.py` 与人工复核承担——这是**有意接受**的边界，见缺口档。

Doc: docs/gaps/gap-feature-scatter.md（步 2 收敛目标与接受边界）
"""
from __future__ import annotations

import ast
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests._rule_codes import all_codes, code_like  # noqa: E402

_INJECTORS = os.path.join(_ROOT, "tests", "e2e", "mutation", "injectors.py")
_BENCHMARK = os.path.join(_ROOT, "tests", "e2e", "eval_benchmark.py")
_DIAG_BASELINE = os.path.join(
    _ROOT, "tests", "e2e", "samples", "real", "diag_baseline.json"
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def defined() -> set[str]:
    return all_codes()


def _kwarg_strings(path: str, names: set[str]) -> set[str]:
    """源码里指定关键字实参的字符串字面量（含 set/tuple 里的元素）。"""
    out: set[str] = set()
    tree = ast.parse(_read(path), filename=path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg not in names:
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                out.add(kw.value.value)
            elif isinstance(kw.value, (ast.Set, ast.Tuple, ast.List)):
                for elt in kw.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        out.add(elt.value)
    return out


def test_mutation_injectors_reference_defined_codes(defined):
    """变异注入器的 `target` / `allowed_extra` 必须指向已定义码。

    指向已删码的注入器**不会报错**——它只是永远不触发，等于静默失效。
    """
    used = _kwarg_strings(_INJECTORS, {"target", "allowed_extra"})
    unknown = sorted(c for c in used if code_like(c) and c not in defined)
    assert not unknown, (
        "变异注入器引用了未定义的诊断码（该变体会静默失效）：\n  "
        + "\n  ".join(unknown)
    )


def test_benchmark_mapping_references_defined_codes(defined):
    """评测基准的 Verilator→tpc 码映射值必须是已定义码（否则评分少算一类）。"""
    tree = ast.parse(_read(_BENCHMARK), filename=_BENCHMARK)
    unknown: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                code = value.value
                if code_like(code) and code not in defined:
                    unknown.add(code)
    assert not unknown, (
        "评测基准映射指向未定义的诊断码：\n  " + "\n  ".join(sorted(unknown))
    )


def test_real_corpus_baseline_only_counts_defined_codes(defined):
    """真实语料误报基线的计数键必须是已定义码（否则基线与现实脱节）。"""
    data = json.loads(_read(_DIAG_BASELINE))
    counts = data.get("counts") or {}
    unknown = sorted(c for c in counts if code_like(c) and c not in defined)
    assert not unknown, (
        "真实语料基线里出现未定义的诊断码（码已删则该键是历史残留，"
        "须按基线更新规程 --update）：\n  " + "\n  ".join(unknown)
    )
