"""eval_lint_accuracy.py — linter 错误发现准确度对照实验。

对 verilog/tests/lint_err/ref/*.v 逐一跑 LinterScanner，与
expected.json 对照表比对，统计错误组检出率/类别准确率 + 合法组误报。

用法:
    python verilog/eval_lint_accuracy.py
    python verilog/eval_lint_accuracy.py --json     # 输出完整 JSON
"""

import os
import sys
import io
import json

# 强制 UTF-8 输出（避免 Windows GBK 控制台报 UnicodeEncodeError）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 项目根（本文件在 <root>/verilog/ 下）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from core.define import DEFAULT_RULES_DIR
from linter.scanner import LinterScanner

_LINT_DIR = os.path.join("verilog", "tests", "lint_err")
_REF_DIR = os.path.join(_LINT_DIR, "ref")
_EXPECT_PATH = os.path.join(_LINT_DIR, "expected.json")


def main() -> None:
    with open(_EXPECT_PATH, "r", encoding="utf-8") as f:
        table = json.load(f)

    scanner = LinterScanner(DEFAULT_RULES_DIR)

    rows = []
    stats = {
        "err_total": 0,       # 错误样本（linter 应检出，非 external）总数
        "detected": 0,        # 错误样本被检出（>=1 诊断）
        "hit_code": 0,        # 检出且类别命中期望
        "detected_badcode": 0,  # 检出但类别不符
        "miss": 0,            # 漏检（0 诊断）
        "ext_total": 0,       # 外部依赖类（preprocessor/lexer）样本数
        "ext_detected": 0,    # 外部依赖类被检出
        "valid_total": len(table["valid"]),
        "fp": 0,              # 合法样本误报
    }

    # ── 错误样本 ──────────────────────────────
    for fname, meta in table["samples"].items():
        path = os.path.join(_REF_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        errs = scanner.scan(src)
        codes = [e.code for e in errs]
        expect = meta["expect"]
        is_ext = meta.get("category") == "external"

        if is_ext:
            # 外部依赖类（未定义宏等，需 preprocessor/lexer 配合）：单列，不入主 recall
            stats["ext_total"] += 1
            if len(errs) > 0:
                stats["ext_detected"] += 1
                verdict = "HIT"
            else:
                verdict = "EXTERNAL-MISS"
        else:
            stats["err_total"] += 1
            if len(errs) == 0:
                verdict = "MISS"
                stats["miss"] += 1
            else:
                stats["detected"] += 1
                hit = any(c in expect for c in codes)
                if hit:
                    verdict = "HIT"
                    stats["hit_code"] += 1
                else:
                    verdict = "DETECTED-BADCODE"
                    stats["detected_badcode"] += 1

        rows.append({
            "file": fname,
            "desc": meta["desc"],
            "expect": expect,
            "codes": codes,
            "n": len(errs),
            "verdict": verdict,
        })

    # ── 合法样本（误报） ──────────────────────
    for fname, meta in table["valid"].items():
        path = os.path.join(_REF_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        errs = scanner.scan(src)
        codes = [e.code for e in errs]
        rows.append({
            "file": fname,
            "desc": meta["desc"],
            "expect": [],
            "codes": codes,
            "n": len(errs),
            "verdict": "FP" if len(errs) > 0 else "OK",
        })
        if len(errs) > 0:
            stats["fp"] += 1

    # ── 汇总 ──────────────────────────────────
    err_total = stats["err_total"]
    detected = stats["detected"]
    miss = stats["miss"]
    hit = stats["hit_code"]
    badcode = stats["detected_badcode"]
    valid_total = stats["valid_total"]
    fp = stats["fp"]

    summary = {
        "错误样本总数": err_total,
        "检出（>=1 诊断）": detected,
        "  类别正确检出 (HIT)": hit,
        "  检出但类别不符": badcode,
        "漏检 (0 诊断)": miss,
        "检出率 recall": f"{detected / err_total:.1%}" if err_total else "n/a",
        "类别准确率 (HIT/检出)": f"{hit / detected:.1%}" if detected else "n/a",
        "外部依赖类 (preprocessor/lexer)": f"{stats['ext_detected']}/{stats['ext_total']} 检出",
        "合法样本总数": valid_total,
        "误报 FP": fp,
        "误报率": f"{fp / valid_total:.1%}" if valid_total else "n/a",
        "精确率 precision (1-FP率)": f"{1 - fp / valid_total:.1%}" if valid_total else "n/a",
    }

    # ── 输出 ──────────────────────────────────
    if "--json" in sys.argv:
        print(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2))
        return

    print("=" * 96)
    print("linter 错误发现准确度对照实验")
    print("=" * 96)
    print(f"{'样本':<26}{'判定':<18}{'n':<4}{'期望':<32}{'实际 code'}")
    print("-" * 96)
    for r in rows:
        tag = {"HIT": "HIT ✅", "MISS": "MISS ❌", "DETECTED-BADCODE": "BADCODE ⚠",
               "OK": "OK ✅", "FP": "FP ❌",
               "EXTERNAL-MISS": "EXT-MISS ⚠"}[r["verdict"]]
        print(f"{r['file']:<26}{tag:<18}{r['n']:<4}{str(r['expect']):<32}{','.join(r['codes'])[:34]}")
    print("=" * 96)
    for k, v in summary.items():
        print(f"{k:<28}{v}")


if __name__ == "__main__":
    main()
