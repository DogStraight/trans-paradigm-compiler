"""eval_mutation.py — 变异注入器评测（检查能力检验：错误类型 → 检出）。

对 tests/e2e/mutation/injectors.py 的每条注入器：
1. **基座洁净**：正确基座跑默认启用集（default=true ∪ 注入器 enable）
   必须零诊断（基座不干净 = 注入无效，测试失败）；
2. **注入后检出**：变异源码（单个特定错误）→ 目标检查必须检出
   （recall 断言）；
3. **无他检误报**：变异后诊断 ⊆ {目标} ∪ allowed_extra（注入只引入
   目标错误，其他检查不误报）。

统计：注入器总数 / 目标检出（recall）/ 基座不干净 / 注入后多余诊断 /
解析失败（变异破坏了语法 = 注入失败，非漏检）。

用法:
    python tests/e2e/eval_mutation.py
    python tests/e2e/eval_mutation.py --json
"""

import io
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from analyzer.checker import ProjectChecker
from core import check_registry
from tests.e2e.mutation.injectors import INJECTORS


def _codes(report) -> set:
    return {
        d.get("code")
        for f in report.get("files", [])
        for d in f.get("semantic", [])
        if d.get("code")
    }


def _parse_ok(report) -> bool:
    return all(
        f.get("parse_ok") and not f.get("syntax") for f in report.get("files", [])
    )


def _check_src(checker, src: str, tmpdir) -> set:
    """源码 → 临时文件 → check → 诊断码集合。"""
    path = os.path.join(tmpdir, "mutation_case.sv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return _codes(checker.check(path))


def evaluate(checker) -> tuple[list[dict], dict]:
    """跑全部注入器，返回 (rows, summary)。"""
    default_on = {
        r.get("id", "")
        for r in check_registry.get_check_rules()
        if r.get("default", True)
    }
    rows = []
    stats = {
        "total": 0,           # 注入器总数
        "recall_hit": 0,      # 目标检查检出
        "recall_miss": 0,     # 目标检查漏检
        "base_dirty": 0,      # 基座不干净（注入无效）
        "extra_fp": 0,        # 注入后多余诊断（非目标非 allowed）
        "parse_fail": 0,      # 变异后语法失败（注入失败）
    }
    per_target: dict[str, dict] = {}

    for inj in INJECTORS:
        stats["total"] += 1
        target = inj["target"]
        enabled = sorted(default_on | set(inj.get("enable", [])))
        checker._enabled_rules = enabled
        tmpdir = tempfile.mkdtemp(prefix="tpc_mut_")
        try:
            base_codes = _check_src(checker, inj["base"], tmpdir)
            if base_codes:
                stats["base_dirty"] += 1
                rows.append({**inj, "verdict": "BASE-DIRTY",
                             "base_codes": sorted(base_codes)})
                continue

            mutated = inj["mutate"](inj["base"])
            if mutated == inj["base"]:
                raise ValueError(f"注入器 {inj['id']}: mutate 未改变源码（注入无效）")
            # 同名文件覆写为变异源码再跑
            with open(os.path.join(tmpdir, "mutation_case.sv"), "w",
                      encoding="utf-8") as f:
                f.write(mutated)
            report = checker.check(os.path.join(tmpdir, "mutation_case.sv"))
            codes = _codes(report)

            if not _parse_ok(report):
                stats["parse_fail"] += 1
                rows.append({**inj, "verdict": "PARSE-FAIL",
                             "codes": sorted(codes)})
                continue

            entry = per_target.setdefault(target, {"total": 0, "hit": 0})
            entry["total"] += 1
            if target in codes:
                entry["hit"] += 1
                stats["recall_hit"] += 1
            else:
                stats["recall_miss"] += 1

            extras = codes - {target} - set(inj.get("allowed_extra", []))
            if extras:
                stats["extra_fp"] += 1
            verdict = "HIT" if target in codes and not extras else (
                "MISS" if target not in codes else "FP-EXTRA"
            )
            rows.append({
                "id": inj["id"],
                "target": target,
                "verdict": verdict,
                "codes": sorted(codes),
                "allowed_extra": sorted(inj.get("allowed_extra", [])),
            })
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    summary = {
        "注入器总数": stats["total"],
        "目标检出 (recall)": f"{stats['recall_hit']}/{stats['recall_miss'] + stats['recall_hit']}"
        if (stats["recall_hit"] + stats["recall_miss"])
        else "n/a",
        "基座不干净": stats["base_dirty"],
        "注入后多余诊断 (FP)": stats["extra_fp"],
        "变异后解析失败": stats["parse_fail"],
        "total": stats["total"],
        "recall_hit": stats["recall_hit"],
        "recall_miss": stats["recall_miss"],
        "base_dirty": stats["base_dirty"],
        "extra_fp": stats["extra_fp"],
        "parse_fail": stats["parse_fail"],
        "per_target": {
            code: {"total": v["total"], "hit": v["hit"]}
            for code, v in sorted(per_target.items())
        },
    }
    return rows, summary


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    os.chdir(_ROOT)
    checker = ProjectChecker(rules_dir="grammar/verilog")
    rows, summary = evaluate(checker)
    if "--json" in sys.argv:
        print(__import__("json").dumps({"rows": rows, "summary": summary},
                                       ensure_ascii=False, indent=2))
        return
    print("=" * 90)
    print("变异注入器评测（检查能力：错误类型 → 检出）")
    print("=" * 90)
    for r in rows:
        tag = {"HIT": "HIT ✅", "MISS": "MISS ❌", "FP-EXTRA": "FP ❌",
               "BASE-DIRTY": "BASE-DIRTY ⚠", "PARSE-FAIL": "PARSE-FAIL ⚠"}[r["verdict"]]
        print(f"{r.get('id', r.get('name', '')):<32}{r.get('target', ''):<8}"
              f"{tag:<14}{','.join(r.get('codes', []))[:40]}")
    print("=" * 90)
    for k, v in summary.items():
        print(f"{k:<22}{v}")


if __name__ == "__main__":
    main()
