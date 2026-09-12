"""eval_diag_baseline.py — 真实语料诊断计数基线（防误报面无声增长）。

Doc: docs/references.md（多 oracle 对拍结论）

动机：规则的默认开/关是"数据决策"，但真实语料上的误报面此前只有**人工
量化**、无留存记录 → 规则改动导致的误报增长只能靠人偶然发现。本脚本把
真实语料上的诊断计数（按码）固化成基线文件，任何增长都会在门禁里显形。

设计取舍：
- **不依赖 oracle**：基线只存 tpc 自身计数——"增长即需解释"这个性质不需要
  判定对错；查证哪些是误报用 `eval_benchmark.py`（需外部工具，故不进日常
  门禁，仍由人工按需跑）。
- **允许减少、禁止增加**：修好规则使计数下降是好事，自动通过；增加则失败并
  列出增量——要求"要么修，要么显式更新基线并说明原因"。
- **分组口径单一来源**：语料与工程分组复用 `eval_benchmark._GROUPS`
  （uart 三文件一个工程），避免同一口径出现第二份实现。
- 计数按**条数**（不是"出现过哪些码"）：与 `eval_check_accuracy._collect_codes`
  的去重收集语义不同，故自写收集，但共用同一 report 结构。

用法：
    python tests/e2e/eval_diag_baseline.py            # 比对当前 vs 基线
    python tests/e2e/eval_diag_baseline.py --json     # 输出 JSON
    python tests/e2e/eval_diag_baseline.py --update   # 重写基线（需说明原因）
"""

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from analyzer.checker import ProjectChecker  # noqa: E402

from tests.e2e.eval_benchmark import _GROUPS, _REAL_DIR  # noqa: E402

_BASELINE_PATH = os.path.join("tests", "e2e", "samples", "real", "diag_baseline.json")


def collect(checker=None) -> dict[str, int]:
    """跑真实语料全部工程，返回 {code: 条数}（升序键）。"""
    if checker is None:
        checker = ProjectChecker(rules_dir="grammar/verilog")
    counts: dict[str, int] = {}
    for group in _GROUPS:
        # 整组喂（多入口）：一次 check 共享 module_index，跨目录的工程才
        # 能互相看见单元定义（单入口只搜索入口所在目录 + include 目录）。
        entry = [os.path.join(_REAL_DIR, f) for f in group["files"]]
        report = checker.check(entry)
        for f in report.get("files", []):
            for d in f.get("semantic", []):
                code = d.get("code")
                if code:
                    counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def load_baseline(path: str = _BASELINE_PATH) -> dict:
    with open(os.path.join(_ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def compare(current: dict[str, int], baseline: dict[str, int]) -> tuple[dict, dict, dict]:
    """返回 (新增/增长, 减少/消失, 持平)——键均为规则码。"""
    grew: dict[str, tuple[int, int]] = {}
    shrank: dict[str, tuple[int, int]] = {}
    same: dict[str, int] = {}
    for code in sorted(set(current) | set(baseline)):
        now = current.get(code, 0)
        was = baseline.get(code, 0)
        if now > was:
            grew[code] = (was, now)
        elif now < was:
            shrank[code] = (was, now)
        else:
            same[code] = now
    return grew, shrank, same


def write_baseline(counts: dict[str, int], path: str = _BASELINE_PATH) -> str:
    data = {
        "_note": (
            "真实语料诊断计数基线（按码计条数）。增长即需解释：先确认是修复"
            "带来的真诊断还是误报回归；确需更新时用 --update 并说明原因。"
        ),
        "corpus": "tests/e2e/samples/real/ref（工程分组同 eval_benchmark._GROUPS）",
        "total": sum(counts.values()),
        "counts": counts,
    }
    target = os.path.join(_ROOT, path)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return target


def main() -> int:
    os.chdir(_ROOT)
    ap = argparse.ArgumentParser(description="真实语料诊断计数基线")
    ap.add_argument("--update", action="store_true", help="按当前结果重写基线")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    current = collect()
    if args.update:
        target = write_baseline(current)
        print(f"[update] 已写入 {os.path.relpath(target, _ROOT)}（共 {sum(current.values())} 条）")
        for code, n in current.items():
            print(f"  {code:<10} {n}")
        return 0

    if not os.path.isfile(os.path.join(_ROOT, _BASELINE_PATH)):
        print(f"[error] 基线不存在：{_BASELINE_PATH}（先跑 --update）")
        return 2
    data = load_baseline()
    baseline: dict[str, int] = data.get("counts", {})
    grew, shrank, same = compare(current, baseline)

    if args.json:
        print(json.dumps(
            {"current": current, "baseline": baseline,
             "grew": grew, "shrank": shrank},
            ensure_ascii=False, indent=2,
        ))
        return 1 if grew else 0

    print(f"语料：{data.get('corpus', '')}")
    print(f"基线合计 {sum(baseline.values())} 条 → 当前 {sum(current.values())} 条")
    if grew:
        print("\n[FAIL] 以下规则码的诊断条数**增加**（需解释：修复带来的真诊断，还是误报回归？）：")
        for code, (was, now) in grew.items():
            print(f"  {code:<10} {was} → {now}  (+{now - was})")
    if shrank:
        print("\n[note] 以下规则码减少（好事；可用 --update 刷新基线）：")
        for code, (was, now) in shrank.items():
            print(f"  {code:<10} {was} → {now}  ({now - was})")
    if not grew:
        print("\n[OK] 无增长")
    return 1 if grew else 0


if __name__ == "__main__":
    sys.exit(main())
