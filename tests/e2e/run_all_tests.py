#!/usr/bin/env python3
"""
Regression test runner – schedules run_pipeline.py for each test case.
Does not re-implement the pipeline, instead imports and calls run_pipeline_on_source.

Usage:
    python run_all_tests.py                    # all tests
    python run_all_tests.py normal             # normal group only
    python run_all_tests.py errors             # errors group only
    python run_all_tests.py normal counter     # normal/ref_counter only
    python run_all_tests.py -v                 # verbose output
    python run_all_tests.py --json             # JSON report
    python run_all_tests.py --expand-macros    # enable macro expansion
    python run_all_tests.py --inline-comments  # enable inline comment injection
    python run_all_tests.py --no-semantic      # skip analyzer + transform stages
    python run_all_tests.py --no-lint          # skip linter pre-check
"""

import sys
import os
import json
import time
import io
import difflib
import shutil
from typing import Any
from core.define import DEFAULT_EXT_DIRS

# Force stdout to UTF-8
sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)

# Add project root to path for importing pipeline
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def discover_tests(
    base_dir: str, group_filter: str | None = None, name_filter: str | None = None
) -> list[tuple[str, str, str]]:
    """Discover test files. Returns list of (name, full_path, group)."""
    tests_dir = os.path.join(base_dir, "samples")
    cases = []
    groups = [group_filter] if group_filter else ["normal", "errors", "warning", "transform"]
    for group in groups:
        ref_dir = os.path.join(tests_dir, group, "ref")
        if not os.path.isdir(ref_dir):
            continue
        for f in sorted(os.listdir(ref_dir)):
            if not f.endswith(".v") or f.startswith("_"):
                continue
            name = f.replace(".v", "")
            if name_filter and name != name_filter:
                continue
            cases.append((name, os.path.join(ref_dir, f), group))
    return cases


def _strip_all(text: str) -> str:
    """Remove all whitespace, newlines, and comments from text for comparison."""
    lines = []
    for line in text.splitlines():
        # remove inline comments
        ci = line.find("//")
        if ci >= 0:
            line = line[:ci]
        lines.append(line)
    return "".join("".join(lines).split())


def _fidelity_cache_path(base_dir: str, group: str) -> str:
    """Get per-group fidelity cache path."""
    return os.path.join(base_dir, "samples", group, ".fidelity_cache.json")


def _load_fidelity_cache(base_dir: str, group: str) -> dict:
    """Load cached fidelity results from per-group JSON."""
    path = _fidelity_cache_path(base_dir, group)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_fidelity_cache(base_dir: str, group: str, cache: dict) -> None:
    """Save fidelity cache to per-group JSON."""
    path = _fidelity_cache_path(base_dir, group)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def run_all(
    verbose: bool = False,
    json_out: bool = False,
    inline_comments: bool = False,
    expand_macros: bool = False,
    no_semantic: bool = False,
    no_lint: bool = False,
    enable_diff: bool = False,
    group_filter: str | None = None,
    name_filter: str | None = None,
) -> bool:
    """Run all tests and return True if all pass."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Import the core pipeline function (shared context initializes on first call)
    from run_pipeline import run_pipeline_on_source

    cases = discover_tests(base_dir, group_filter, name_filter)
    if not cases:
        print("[error] no test cases found", file=sys.stderr)
        return False

    # ── 清空所有 gen/ 目录 ─────────────────────────────
    for group in set(g for _, _, g in cases):
        gen_dir = os.path.join(base_dir, "samples", group, "gen")
        if os.path.isdir(gen_dir):
            shutil.rmtree(gen_dir)
            print(f"  [setup] cleared {os.path.relpath(gen_dir, base_dir)}/")

    results = []
    total_ok = 0
    total_err = 0
    total_warn = 0
    total_fail = 0
    fidelity_changed: list[tuple[str, float, float]] = []  # (name, old, new)
    t_start = time.time()

    for name, path, group in cases:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()

        out_dir = os.path.join(base_dir, "samples", group)

        # 日志抑制
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        if not verbose:
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
        try:
            result: dict[str, Any] = run_pipeline_on_source(
                source=source,
                input_path=path,
                out_dir=out_dir,
                expand_macros=expand_macros,
                inline_comments=inline_comments,
                quiet=True,
                analyzer_enabled=not no_semantic,
                transform_enabled=not no_semantic,
                renderer_enabled=True,
                stage=None,
                no_lint=no_lint,
                ext_dirs=DEFAULT_EXT_DIRS,
            )
        finally:
            if not verbose:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        success = result["success"]
        err_msg = result["error"] or ""
        post_lint_errors = result.get("post_lint_errors", 0)

        # ── 文本保真度比较（normal / transform 组）────────────────
        # normal 组：ref = 输入文件，保真度 = 管线输出对输入的保留程度
        # transform 组：ref = 正确展开后的输出，保真度 = 管线输出对展开预期的匹配程度
        fidelity = 1.0  # 默认值
        fidelity_dropped = False
        prev_display = fidelity  # 默认值，供块外引用
        if group in ("normal", "transform") and success:
            base_name = name.replace("ref_", "", 1) if name.startswith("ref_") else name
            gen_path = os.path.join(out_dir, "gen", f"gen_{base_name}.v")
            if os.path.exists(gen_path):
                with open(gen_path, "r", encoding="utf-8") as f:
                    gen_content = f.read()

                ref_flat = _strip_all(source)
                gen_flat = _strip_all(gen_content)

                if ref_flat == gen_flat:
                    fidelity = 1.0
                else:
                    fidelity = difflib.SequenceMatcher(None, ref_flat, gen_flat).ratio()
                    fidelity = round(fidelity, 4)

                # 按组加载缓存，检测保真度下降
                group_cache = _load_fidelity_cache(base_dir, group)
                prev = group_cache.get(name)
                if prev is not None and fidelity < prev:
                    fidelity_dropped = True
                    fidelity_changed.append((name, prev, fidelity))

                # 更新缓存：保存最高保真度（下降后不会覆盖缓存）
                prev_display = prev if prev is not None else fidelity
                group_cache[name] = max(prev or 0, fidelity)
                _save_fidelity_cache(base_dir, group, group_cache)

        # 判定测试结果
        if group == "errors":
            passed = not success
        elif group == "warning":
            passed = success
        else:
            # normal/transform 组：管线成功即通过，但保真度下降算 FAIL
            passed = success and not fidelity_dropped

        if passed:
            if group == "errors":
                total_err += 1
                status = "ERR"
            elif group == "warning":
                total_warn += 1
                status = "WARN"
            else:
                if post_lint_errors:
                    total_warn += 1
                    status = "LINT"
                else:
                    total_ok += 1
                    status = "OK"
        else:
            total_fail += 1
            status = "FAIL"

        results.append((name, passed, status, err_msg[:60]))

        # 输出详情
        suffix = ""
        if fidelity < 1.0 and group in ("normal", "transform"):
            suffix = f"  fidelity={fidelity:.4f}"
        if fidelity_dropped:
            suffix += f"  ↓ from {prev_display:.4f}"
        if post_lint_errors:
            suffix += f"  post-lint={post_lint_errors}"
        print(f"  {name:25s} {status:5s} {err_msg[:30]}{suffix}")

    # ── 打印保真度下降汇总 ────────────────────────────
    if fidelity_changed:
        print(f"\n  ⚠  Fidelity drops ({len(fidelity_changed)}):")
        for tc_name, old, new in fidelity_changed:
            print(f"      {tc_name}: {old:.4f} → {new:.4f} (Δ{new-old:+.4f})")

    elapsed = time.time() - t_start
    total = total_ok + total_err + total_fail + total_warn
    print(f"\n{'=' * 40}")
    print(
        f"\n  Total: {total}  OK: {total_ok}  ERR: {total_err}  WARN: {total_warn}  FAIL: {total_fail}  Time: {elapsed:.1f}s"
    )

    if json_out:
        report = {
            "total": total,
            "ok": total_ok,
            "err": total_err,
            "warn": total_warn,
            "fail": total_fail,
            "elapsed": round(elapsed, 2),
            "fidelity_drops": [
                {"case": n, "from": old, "to": new} for n, old, new in fidelity_changed
            ],
            "cases": [
                {"name": n, "ok": ok, "status": status, "error": err}
                for n, ok, status, err in results
            ],
        }
        json_path = os.path.join(base_dir, "test_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  Report saved: {json_path}")

    return total_fail == 0


if __name__ == "__main__":
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    json_out = "--json" in sys.argv
    inline_comments = "--inline-comments" in sys.argv
    expand_macros = "--expand-macros" in sys.argv
    no_semantic = "--no-semantic" in sys.argv
    no_lint = "--no-lint" in sys.argv
    enable_diff = "--diff" in sys.argv  # kept for backward compat, no longer needed

    pos_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    group_filter = pos_args[0] if len(pos_args) >= 1 else None
    name_filter = pos_args[1] if len(pos_args) >= 2 else None

    if group_filter and group_filter not in ("normal", "errors", "warning", "transform"):
        print(f"[error] unknown group: {group_filter} (expected normal|errors|warning|transform)")
        sys.exit(1)
    if name_filter:
        name_filter = f"ref_{name_filter}".replace(".v", "")

    ok = run_all(
        verbose=verbose,
        json_out=json_out,
        inline_comments=inline_comments,
        expand_macros=expand_macros,
        no_semantic=no_semantic,
        no_lint=no_lint,
        enable_diff=enable_diff,
        group_filter=group_filter,
        name_filter=name_filter,
    )
    sys.exit(0 if ok else 1)
