"""tests/e2e/eval_diag_baseline_c.py — C 真实语料诊断计数基线（判据 5 门禁采集器）。

Doc: docs/gaps/gap-language-pack-scope.md（C 包接受域/门禁清单） / tests/policy/test_diag_baseline_c.py

语料 = `tests/e2e/samples/real_c_ref/ref`（cJSON 1.7.19 + zlib 1.3.2 核心 6 文件；
归属/许可见同目录 `CREDITS.md`），include 面 = `ref` + `stubs` 最小系统头。
口径与 verilog 先例（`eval_diag_baseline.py`）同构：**只许减不许增**——
诊断增长即失败（修规则或显式 `--update` 并说明原因），减少放行并提示刷新。

用法：
    python tests/e2e/eval_diag_baseline_c.py            # 比对当前 vs 基线
    python tests/e2e/eval_diag_baseline_c.py --json     # 输出 JSON
    python tests/e2e/eval_diag_baseline_c.py --update   # 重写基线（需说明原因）
"""

from __future__ import annotations

import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS_DIR = os.path.join(_ROOT, "tests", "e2e", "samples", "real_c_ref")
_REF_DIR = os.path.join(_CORPUS_DIR, "ref")
_STUBS_DIR = os.path.join(_CORPUS_DIR, "stubs")
_BASELINE_PATH = os.path.join("tests", "e2e", "samples", "real_c_ref", "diag_baseline.json")

#: 语料清单（新文件入库时在此登记；CREDITS.md 记来源/版本）
_MANIFEST: tuple[str, ...] = (
    "cJSON.c",
    "zutil.c",
    "crc32.c",
    "adler32.c",
    "compress.c",
    "uncompr.c",
    "gzread.c",
)


def _checker():
    from analyzer.checker import ProjectChecker

    return ProjectChecker(
        rules_dir="grammar/c",
        ext_dirs=None,
        include_dirs=[_REF_DIR, _STUBS_DIR],
    )


def collect(checker=None) -> dict[str, int]:
    """跑 C 真实语料全部文件，返回 {code: 条数}（升序键；syntax 前缀区分两类码）。"""
    if checker is None:
        checker = _checker()
    counts: dict[str, int] = {}
    for name in _MANIFEST:
        report = checker.check(os.path.join(_REF_DIR, name))
        for f in report.get("files", []):
            for d in f.get("syntax", []):
                code = d.get("code")
                if code:
                    key = f"syntax:{code}"
                    counts[key] = counts.get(key, 0) + 1
            for d in f.get("semantic", []):
                code = d.get("code")
                if code:
                    counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def collect_report(checker=None) -> dict:
    """同 `collect()`，但返回完整报告（供门禁做解析完整性 sanity）。

    `parse_ok=True` 在结构阶段 = AST 完整（截断会置 False/parse_error，见
    `analyzer/structure.py::parse_file`）——不是 #43 时代"部分 AST 也 True"的口径。
    """
    if checker is None:
        checker = _checker()
    files: list[dict] = []
    counts: dict[str, int] = {}
    for name in _MANIFEST:
        report = checker.check(os.path.join(_REF_DIR, name))
        for f in report.get("files", []):
            files.append(
                {
                    "name": name,
                    "parse_ok": bool(f.get("parse_ok")),
                    "parse_error": str(f.get("parse_error") or ""),
                }
            )
            for d in f.get("syntax", []):
                code = d.get("code")
                if code:
                    key = f"syntax:{code}"
                    counts[key] = counts.get(key, 0) + 1
            for d in f.get("semantic", []):
                code = d.get("code")
                if code:
                    counts[code] = counts.get(code, 0) + 1
    return {"counts": dict(sorted(counts.items())), "files": files}


def load_baseline(path: str = _BASELINE_PATH) -> dict:
    with open(os.path.join(_ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def compare(current: dict[str, int], baseline: dict[str, int]) -> tuple[dict, dict, dict]:
    """返回 (新增/增长, 减少/消失, 持平)；键均为规则码。"""
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
            "C 真实语料诊断计数基线（按码计条数；syntax: 前缀 = linter 诊断）。"
            "增长即需解释：先确认是修复带来的真诊断还是误报回归；确需更新时用 "
            "--update 并说明原因。目标 = 零诊断（当前 total 0）。"
        ),
        "corpus": "tests/e2e/samples/real_c_ref（ref + stubs；归属/许可见 CREDITS.md）",
        "total": sum(counts.values()),
        "counts": counts,
    }
    target = os.path.join(_ROOT, path)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return target


def main() -> int:
    update = "--update" in sys.argv
    as_json = "--json" in sys.argv
    current = collect()
    if update:
        target = write_baseline(current)
        print(f"[ok] 基线已写入：{target}")
        print(json.dumps({"total": sum(current.values()), "counts": current}, ensure_ascii=False, indent=2))
        return 0
    baseline = load_baseline().get("counts", {})
    grew, shrank, same = compare(current, baseline)
    if as_json:
        print(json.dumps({"current": current, "grew": grew, "shrank": shrank, "same": same},
                         ensure_ascii=False, indent=2))
    else:
        print(f"当前 total={sum(current.values())}，基线 total={sum(baseline.values())}")
        if grew:
            print("[FAIL] 诊断增长：")
            for code, (was, now) in grew.items():
                print(f"  {code}: {was} → {now} (+{now - was})")
        if shrank:
            print("[info] 诊断减少（可刷新基线）：")
            for code, (was, now) in shrank.items():
                print(f"  {code}: {was} → {now} ({now - was})")
        if not grew:
            print("[OK] 无增长（只许减不许增）")
    return 1 if grew else 0


if __name__ == "__main__":
    sys.exit(main())
