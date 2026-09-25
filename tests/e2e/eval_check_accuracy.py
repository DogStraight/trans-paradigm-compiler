"""eval_check_accuracy.py — analyzer 检查规则检出准确度评测（0.1.1 试水）。

对 tests/e2e/samples/check_accuracy/cases/ 下的标注样本逐一跑 ProjectChecker
（跨文件语义检查），与 expected.json 标注比对，统计：

    recall   — 正样例（pos）中期望检出的规则码是否都被检出（漏检 = MISS）
    FP       — 负样例（neg）误报 + 正样例检出的期望外规则码
    precision— 命中 / (命中 + FP)

判定模型（逐 code 集合）：
    pos:  expect 集合 E ⊆ 实际集合 A → 命中；A - E（focus 内）→ FP
    neg:  A ∩ focus 非空 → FP（负样例必须完全干净）

样本目录名 = case id；entry 文件由 expected.json 指定（缺省 top.sv）；
跨文件样本的模块定义文件与 entry 同目录，由 ProjectChecker 递归发现。

用法:
    python tests/e2e/eval_check_accuracy.py
    python tests/e2e/eval_check_accuracy.py --json     # 输出完整 JSON
"""

import io
import json
import os
import sys

# 项目根（本文件在 <root>/tests/e2e/ 下）
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from analyzer.checker import ProjectChecker

_SAMPLE_DIR = os.path.join("tests", "e2e", "samples", "check_accuracy")
_CASES_DIR = os.path.join(_SAMPLE_DIR, "cases")
_EXPECT_PATH = os.path.join(_SAMPLE_DIR, "expected.json")


def sample_stats() -> dict[str, int]:
    """样本规模与覆盖面的**唯一自动来源**（文档引用本函数，不写死数字）。

    动机：同一事实多处陈述会漂移——case 数/期望码数曾在 docstring、
    CHANGELOG、TODO 各写一遍，改一处漏一处（0.1.2 收尾轮同一轮错了三次）。
    故规模数字从 expected.json 现算，文档只引用来源。

    Returns: pos / neg / case（正+负）/ focus（focus 码数）/ expect_codes
             （期望码条目总数——一个 case 可期望多码）
    """
    table = _load_table()
    pos = table.get("pos", {})
    neg = table.get("neg", {})
    return {
        "pos": len(pos),
        "neg": len(neg),
        "case": len(pos) + len(neg),
        "focus": len(table.get("focus", [])),
        "expect_codes": sum(len(m.get("expect", [])) for m in pos.values()),
    }


def _load_table() -> dict:
    with open(_EXPECT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _collect_codes(report: dict) -> list[str]:
    """收集 report 全部文件的语义诊断 code（去重保序）。"""
    codes: list[str] = []
    seen: set[str] = set()
    for f in report.get("files", []):
        for d in f.get("semantic", []):
            code = d.get("code")
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def evaluate(checker, table=None) -> tuple[list[dict], dict]:
    """对全部样本跑 ProjectChecker，返回 (rows, summary)。

    rows: 每样本一行 {case, kind, desc, expect, codes, n, verdict}；
          verdict ∈ {HIT, MISS, FP, OK, PARSE-ERR}。
    summary: recall / FP / precision 原始计数 + 格式化 + 逐规则 recall。
    --json 打印与 pytest 断言都基于本函数返回，判定逻辑单一来源。
    """
    if table is None:
        table = _load_table()
    focus: set[str] = set(table.get("focus", []))
    # focus 规则显式启用（含默认关闭的 NC 族——评测验证"启用后"的
    # 检出能力，不受语言包默认策略影响）
    checker._enabled_rules = sorted(focus)

    rows = []
    stats = {
        "pos_total": 0,      # 正样例数
        "expect_codes": 0,   # 期望检出规则码总数（一个样本可期望多个）
        "hit": 0,            # 期望码被检出
        "miss": 0,           # 期望码漏检
        "neg_total": 0,      # 负样例数
        "fp": 0,             # 误报规则码数（pos 额外 + neg 检出）
        "parse_err": 0,      # 解析失败样本（语义阶段被跳过，全部 MISS）
    }
    per_rule: dict[str, dict] = {}  # code -> {total, hit}

    def _note(code: str, hit: bool) -> None:
        entry = per_rule.setdefault(code, {"total": 0, "hit": 0})
        entry["total"] += 1
        if hit:
            entry["hit"] += 1

    # ── 正样例（应检出）──────────────────────────────
    for case_id, meta in table.get("pos", {}).items():
        entry = os.path.join(_CASES_DIR, case_id)
        path = os.path.join(entry, meta.get("entry", "top.sv"))
        report = checker.check(path)
        actual = _collect_codes(report)
        expect = list(meta.get("expect", []))
        stats["pos_total"] += 1
        stats["expect_codes"] += len(expect)

        parse_fail = any(
            not f.get("parse_ok") for f in report.get("files", [])
        ) or any(f.get("syntax") for f in report.get("files", []))

        missed = [c for c in expect if c not in actual]
        extra = sorted(set(actual) & focus - set(expect))
        for c in expect:
            _note(c, c in actual)
        stats["hit"] += len(expect) - len(missed)
        stats["miss"] += len(missed)
        stats["fp"] += len(extra)
        if parse_fail:
            stats["parse_err"] += 1

        verdict = "HIT" if not missed and not extra else ("MISS" if missed else "FP")
        if parse_fail:
            verdict = "PARSE-ERR"
        rows.append({
            "case": case_id,
            "kind": "pos",
            "desc": meta.get("desc", ""),
            "expect": expect,
            "codes": actual,
            "n": len(actual),
            "parse_fail": parse_fail,
            "missed": missed,
            "extra": extra,
            "verdict": verdict,
        })

    # ── 负样例（不应检出 focus 内任何规则）────────────
    for case_id, meta in table.get("neg", {}).items():
        entry = os.path.join(_CASES_DIR, case_id)
        path = os.path.join(entry, meta.get("entry", "top.sv"))
        report = checker.check(path)
        actual = _collect_codes(report)
        stats["neg_total"] += 1

        fp_codes = sorted(set(actual) & focus)
        stats["fp"] += len(fp_codes)
        parse_fail = any(
            not f.get("parse_ok") for f in report.get("files", [])
        ) or any(f.get("syntax") for f in report.get("files", []))

        verdict = "FP" if fp_codes else ("PARSE-ERR" if parse_fail else "OK")
        rows.append({
            "case": case_id,
            "kind": "neg",
            "desc": meta.get("desc", ""),
            "expect": [],
            "codes": actual,
            "n": len(actual),
            "parse_fail": parse_fail,
            "missed": [],
            "extra": fp_codes,
            "verdict": verdict,
        })

    # ── 汇总 ──────────────────────────────────────────
    hit = stats["hit"]
    miss = stats["miss"]
    fp = stats["fp"]
    total_expect = stats["expect_codes"]
    summary = {
        "正样例数": stats["pos_total"],
        "期望规则码总数": total_expect,
        "命中 (HIT)": hit,
        "漏检 (MISS)": miss,
        "检出率 recall": f"{hit / total_expect:.1%}" if total_expect else "n/a",
        "负样例数": stats["neg_total"],
        "误报规则码数 (FP)": fp,
        "误报率 (FP/负样例)": f"{fp / stats['neg_total']:.1%}" if stats["neg_total"] else "n/a",
        "精确率 precision (命中/命中+FP)": (
            f"{hit / (hit + fp):.1%}" if (hit + fp) else "n/a"
        ),
        "解析失败样本": stats["parse_err"],
        # 程序化断言用原始计数
        "pos_total": stats["pos_total"],
        "expect_codes": total_expect,
        "hit": hit,
        "miss": miss,
        "neg_total": stats["neg_total"],
        "fp": fp,
        "parse_err": stats["parse_err"],
        "per_rule": {
            code: {"total": v["total"], "hit": v["hit"]}
            for code, v in sorted(per_rule.items())
        },
    }
    return rows, summary


def main() -> None:
    # 强制 UTF-8 输出（避免 Windows GBK 控制台报 UnicodeEncodeError）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    os.chdir(_ROOT)

    checker = ProjectChecker(rules_dir="grammar/verilog")
    rows, summary = evaluate(checker)

    if "--json" in sys.argv:
        print(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2))
        return

    print("=" * 100)
    print("analyzer 检查规则检出准确度评测（P1.10 核心检查集）")
    print("=" * 100)
    print(f"{'case':<26}{'判定':<14}{'n':<4}{'期望':<26}{'实际 code'}")
    print("-" * 100)
    for r in rows:
        tag = {"HIT": "HIT ✅", "MISS": "MISS ❌", "FP": "FP ❌",
               "OK": "OK ✅", "PARSE-ERR": "PARSE-ERR ⚠"}[r["verdict"]]
        print(f"{r['case']:<26}{tag:<14}{r['n']:<4}{str(r['expect']):<26}{','.join(r['codes'])[:30]}")
    print("=" * 100)
    for k, v in summary.items():
        print(f"{k:<28}{v}")


if __name__ == "__main__":
    main()
