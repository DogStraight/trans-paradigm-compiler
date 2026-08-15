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

# Add project root to path for importing pipeline（必须在 import core 之前）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.define import DEFAULT_EXT_DIRS

# Force stdout to UTF-8
sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)


# ── 组别独立参数配置 ─────────────────────────────────
# errors/lint_err：坏输入，管线应失败（linter 前置抓设定的错误）
# macro：预处理器展开与还原（展开路径，内容变化是预期，不测幂等）
# normal/real：解析能力（real 为真实工业项目，强制展开条件编译）
# transform：天然两条路径——默认非展开（测增强语法保留 + 幂等）；
#   样例含指令时走展开路径（内容变，不测幂等，由 run_pipeline 内建判定）
# warning：语义错误捕获（analyzer 警告不阻断管线）
GROUP_PARAMS: dict[str, dict] = {
    "normal": {"expand_macros": False},
    "errors": {"expand_macros": False},
    "lint_err": {"expand_macros": False},
    "macro": {"expand_macros": True},
    "warning": {"expand_macros": False},
    "transform": {"expand_macros": False},
    "real": {"expand_macros": True},
}


def discover_tests(
    base_dir: str, group_filter: str | None = None, name_filter: str | None = None
) -> list[tuple[str, str, str]]:
    """Discover test files. Returns list of (name, full_path, group)."""
    tests_dir = os.path.join(base_dir, "samples")
    cases = []
    groups = (
        [group_filter]
        if group_filter
        else ["normal", "errors", "lint_err", "macro", "warning", "transform", "real"]
    )
    for group in groups:
        # transform 组：ref/ = 增强语法源（源头，人工维护），trans/ = 展开后预期（生成）
        src_dir = os.path.join(tests_dir, group, "ref")
        if not os.path.isdir(src_dir):
            continue
        for f in sorted(os.listdir(src_dir)):
            if not f.endswith(".v") or f.startswith("_"):
                continue
            name = f.replace(".v", "")
            if name_filter:
                expect = name_filter.removeprefix("ref_") if group == "transform" else name_filter
                if name != expect:
                    continue
            cases.append((name, os.path.join(src_dir, f), group))
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
            if group == "transform":
                # transform 分支自行跑两条路径（见下），跳过公共单路径调用
                result = {"success": True, "error": "", "idempotent": True}
            else:
                # 组别独立参数：宏展开按 GROUP_PARAMS 配置，CLI --expand-macros 可覆盖
                params = GROUP_PARAMS.get(group, {})
                effective_expand = params.get("expand_macros", False) or expand_macros
                result: dict[str, Any] = run_pipeline_on_source(
                    source=source,
                    input_path=path,
                    out_dir=out_dir,
                    expand_macros=effective_expand,
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
        idempotent = result.get("idempotent", True)

        # ── transform 组：两条路径 ────────────────────────
        # 1. 不变换直接渲染（expand_enhanced=False）→ 保真度对比输入（增强语法保留）
        # 2. 变换展开后渲染（expand_enhanced=True）→ 保真度对比 ref（展开正确性）
        if group == "transform":
            subs = []
            idp_bad = False
            all_pass = True
            for mode, eh in (("P", False), ("X", True)):
                r_t = run_pipeline_on_source(
                    source=source,
                    input_path=path,
                    out_dir=out_dir,
                    expand_macros=False,
                    inline_comments=inline_comments,
                    quiet=True,
                    analyzer_enabled=not no_semantic,
                    transform_enabled=not no_semantic,
                    renderer_enabled=True,
                    stage=None,
                    no_lint=no_lint,
                    ext_dirs=DEFAULT_EXT_DIRS,
                    expand_enhanced=eh,
                    # 变换路径禁用注释恢复：变换改变结构后锚点漂移，
                    # 恢复注定找不到位置或误匹配拆坏注释行
                    enable_line_comment_restore=not eh,
                )
                if mode == "P":
                    ref_text = source  # 增强语法保留：对比输入
                    thr = 0.99  # token 完整，应接近 1.0
                else:
                    # X 路径（展开后）：对比 trans/trans_<name>.v（展开预期）
                    # name 带 ref_ 前缀（如 ref_spi_inf）→ trans_<去前缀>（trans_spi_inf）
                    x_name = "trans_" + name.removeprefix("ref_")
                    ref_path = os.path.join(
                        base_dir, "samples", "transform", "trans", f"{x_name}.v"
                    )
                    if not os.path.isfile(ref_path):
                        # 兼容：trans/ 未生成时回退到 ref/ 本身（只有 P 路径断言）
                        ref_path = path
                    with open(ref_path, encoding="utf-8") as f:
                        ref_text = f.read()
                    thr = 0.95  # 展开正确性：实例名 hash 差异可容忍
                t_out = r_t.get("output", "")
                rf, gf = _strip_all(ref_text), _strip_all(t_out)
                t_fid = (
                    1.0
                    if rf == gf
                    else round(difflib.SequenceMatcher(None, rf, gf).ratio(), 4)
                )
                t_pass = bool(r_t.get("success")) and t_fid >= thr
                all_pass = all_pass and t_pass
                if not r_t.get("idempotent", True):
                    idp_bad = True
                subs.append(f"{mode}:{'OK' if t_pass else 'FAIL'}({t_fid:.4f})")
            if idp_bad:
                total_warn += 1
                status = "IDP"
            elif all_pass:
                total_ok += 1
                status = "OK"
            else:
                total_fail += 1
                status = "FAIL"
            results.append((name, all_pass and not idp_bad, status, " ".join(subs)))
            print(f"  {name:25s} {status:5s} {' '.join(subs)}")
            continue

        # ── 文本保真度比较（normal / transform / real 组）────────────────
        # normal 组：ref = 输入文件，保真度 = 管线输出对输入的保留程度
        # transform 组：ref = 正确展开后的输出，保真度 = 管线输出对展开预期的匹配程度
        # real 组：ref = 真实项目输入，保真度 = 输出对输入的 token 级保留程度
        # 缓存 key 带展开模式后缀（expand/plain）：同一样例两种模式的保真值
        # 独立记忆，防止 --expand-macros 与默认模式互串（曾 concat_nest 被
        # 展开模式的高保真污染，默认模式误报 drop）。
        fidelity = 1.0  # 默认值
        fidelity_dropped = False
        prev_display = fidelity  # 默认值，供块外引用
        if group in ("normal", "transform", "real") and success:
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

                # 按组 + 展开模式加载缓存，检测保真度下降
                mode = "expand" if effective_expand else "plain"
                cache_key = f"{name}@{mode}"
                group_cache = _load_fidelity_cache(base_dir, group)
                prev = group_cache.get(cache_key)
                if prev is not None and fidelity < prev:
                    fidelity_dropped = True
                    fidelity_changed.append((name, prev, fidelity))

                # 更新缓存：保存最高保真度（下降后不会覆盖缓存）
                prev_display = prev if prev is not None else fidelity
                group_cache[cache_key] = max(prev or 0, fidelity)
                _save_fidelity_cache(base_dir, group, group_cache)

        # 判定测试结果
        if group in ("errors", "lint_err"):
            # 坏输入组：linter 前置应抓到设定的错误 → 管线失败。
            # lint_err 组含 ref_v* 合法对照样例（验证 linter 无误报）→ 应通过
            passed = success if name.startswith("ref_v") else not success
        elif group == "warning":
            # 语义警告组：analyzer 警告不阻断 → 管线成功
            passed = success
        else:
            # normal/macro/transform/real 组：管线成功即通过，但保真度下降算 FAIL
            passed = success and not fidelity_dropped

        if passed:
            if group in ("errors", "lint_err"):
                if name.startswith("ref_v"):
                    total_ok += 1
                    status = "OK"  # ref_v* 合法对照：linter 无误报
                else:
                    total_err += 1
                    status = "ERR"  # ref_e* 设定的错误：linter 抓到
            elif group == "warning":
                total_warn += 1
                status = "WARN"
            else:
                if not idempotent:
                    total_warn += 1
                    status = "IDP"
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
        if not idempotent:
            suffix += "  idempotent=FAIL"
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

    if group_filter and group_filter not in GROUP_PARAMS:
        print(
            f"[error] unknown group: {group_filter} "
            f"(expected {'|'.join(GROUP_PARAMS)})"
        )
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
