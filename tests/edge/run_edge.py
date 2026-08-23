"""run_edge.py — 边缘构造门禁（recall/FP 纪律，对齐 eval_lint_accuracy）。

语料约定：
    tests/edge/edge_corpus/clean/*.v   — 必须格式化成功（recall 侧）
    tests/edge/edge_corpus/reject/*.v  — 必须失败且不崩溃（FP 侧）

新增语料纪律：fuzz 找到的 bug 最小化后沉淀为 clean/ 或 reject/ 文件，
成为回归（本门禁进 CI）。

用法：
    python tests/edge/run_edge.py
    退出码：0 = 全部符合预期；1 = 有 clean 失败或 reject 误通过
"""

from __future__ import annotations

import os
import sys

# 仓库根引导（脚本从 tests/edge/ 运行时保证 import 可用）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from pipeline import run_pipeline_on_source

_CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_corpus")
_CLEAN = os.path.join(_CORPUS, "clean")
_REJECT = os.path.join(_CORPUS, "reject")


def _fmt(source: str) -> dict:
    """与 format 指令同参（与 fuzz harness 一致）。"""
    return run_pipeline_on_source(
        source=source,
        quiet=True,
        expand_macros=True,
        analyzer_enabled=False,
        transform_enabled=False,
        renderer_enabled=True,
        parse_enabled=True,
        no_lint=False,
        format_output=True,
    )


def _list_v(d: str) -> list[str]:
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".v"))


def main() -> None:
    failures: list[str] = []
    n_clean = n_reject = 0

    print("== clean（必须格式化成功）==")
    for name in _list_v(_CLEAN):
        n_clean += 1
        with open(os.path.join(_CLEAN, name), encoding="utf-8") as f:
            src = f.read()
        try:
            r = _fmt(src)
        except Exception as exc:
            failures.append(f"[CRASH] clean/{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL {name}: crash")
            continue
        if r.get("success"):
            print(f"  ok   {name}")
        else:
            failures.append(f"[CLEAN-FAIL] clean/{name}: {r.get('error')}")
            print(f"  FAIL {name}: {r.get('error')}")

    print("== reject（必须失败且不崩溃）==")
    for name in _list_v(_REJECT):
        n_reject += 1
        with open(os.path.join(_REJECT, name), encoding="utf-8") as f:
            src = f.read()
        try:
            r = _fmt(src)
        except Exception as exc:
            failures.append(f"[CRASH] reject/{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL {name}: crash")
            continue
        if r.get("success"):
            failures.append(f"[REJECT-PASSED] reject/{name}: 本应失败却成功")
            print(f"  FAIL {name}: 应失败却成功")
        else:
            print(f"  ok   {name} ({r.get('error', '')[:60]})")

    print(f"\nclean: {n_clean}  reject: {n_reject}  failures: {len(failures)}")
    if failures:
        for f_ in failures:
            print("  " + f_)
        sys.exit(1)
    print("OK — edge corpus behaves as expected")


if __name__ == "__main__":
    main()
