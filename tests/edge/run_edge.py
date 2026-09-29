"""run_edge.py — 边缘构造门禁（recall/FP 纪律，对齐 eval_lint_accuracy）。

语料约定：
    <corpus>/clean/*.v   — 必须格式化成功（recall 侧）
    <corpus>/reject/*.v  — 必须失败且不崩溃（FP 侧）

新增语料纪律：fuzz 找到的 bug 最小化后沉淀为 clean/ 或 reject/ 文件，
成为回归（本门禁进 CI）。`--corpus` 可指向别的语言包语料（如 C 包），
目录布局同上——见 `tests/fuzz/README.md`「回馈链路」。

用法：
    python tests/edge/run_edge.py
    python tests/edge/run_edge.py --corpus tests/edge/edge_corpus_c --pack grammar/c
    退出码：0 = 全部符合预期；1 = 有 clean 失败或 reject 误通过
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# 仓库根引导（脚本从 tests/edge/ 运行时保证 import 可用）
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_REPO, os.path.join(_REPO, "tests", "fuzz")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import oracle  # noqa: E402  (tests/fuzz/oracle.py：不变量/管线单一来源)

# Windows 控制台/管道默认编码（GBK/cp1252）编不了中文——CI runner 无
# PYTHONUTF8，非 ASCII 输出会让门禁脚本自己崩。本进程自护 stdout/stderr
# （reconfigure 只影响本进程，比替换 sys.stdout 安全；受限环境拒绝则忽略）。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue] — hasattr 守卫的真实运行时方法
        sys.stderr.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:  # noqa: BLE001 — 受限环境无 reconfigure，忽略
        pass

_CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_corpus")
_CLEAN = os.path.join(_CORPUS, "clean")
_REJECT = os.path.join(_CORPUS, "reject")
_DEFAULT_PACK = "grammar/verilog"


def _fmt(source: str, pack: str) -> dict:
    """与 format 指令同参（与 fuzz harness 共用 `oracle.format_source`）。"""
    return oracle.format_source(source, pack)


# 沉淀语料的抬头里带 `fuzz 类别 <kind>`：该类别的不变量从此成为这条语料的**回归判据**
# ——只断言 clean/reject 挡不住"仍非幂等"这类活缺陷（实测：非幂等样本 success=True，
# 只按 clean/reject 判会一路绿灯）。手写语料没有这个标记，只走 clean/reject。
_KIND_RE = re.compile(r"fuzz 类别 ([a-z-]+)")


def _fuzz_kind(src: str) -> str | None:
    m = _KIND_RE.search(src[:400])
    return m.group(1) if m else None


def _list_corpus(d: str, exts: tuple[str, ...]) -> list[str]:
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(exts))


def _kind_violation(src: str, pack: str, name: str, failures: list[str]) -> str | None:
    """沉淀语料的**不变量**回归判据：抬头登记的类别必须已不复现。

    返回被守住的类别名（无标记 = None）。违反则登记失败并回 None（clean/reject
    那两条判据已经报过错了，这里不重复报，只补记不变量那条）。
    """
    kind = _fuzz_kind(src)
    if not kind:
        return None
    from lexer import Lexer

    ext_dirs = oracle.ext_dirs_for(pack)
    kinds = {
        v.kind
        for v in oracle.evaluate_format(
            src, Lexer(rules_dir=pack, ext_dirs=ext_dirs),
            rules_dir=pack, ext_dirs=ext_dirs, label="gen",
        )
    }
    if kind in kinds:
        failures.append(
            f"[INVARIANT-REGRESSED] {name}: 抬头登记的 {kind} 又复现了"
        )
        return None
    return kind


def main() -> None:
    ap = argparse.ArgumentParser(description="边缘构造门禁")
    ap.add_argument("--corpus", default=_CORPUS)
    ap.add_argument("--pack", "--rules-dir", dest="pack", default=_DEFAULT_PACK)
    ap.add_argument("--ext", action="append", default=None,
                    help="语料后缀（可重复；默认按语言包：c→.c/.h，其余 .v）")
    args = ap.parse_args()

    exts = tuple(args.ext) if args.ext else (
        (".c", ".h") if os.path.basename(os.path.normpath(args.pack)) == "c" else (".v",)
    )
    clean_dir = os.path.join(args.corpus, "clean")
    reject_dir = os.path.join(args.corpus, "reject")

    failures: list[str] = []
    n_clean = n_reject = 0

    print(f"pack: {args.pack}  corpus: {args.corpus}  后缀: {exts}")
    print("== clean（必须格式化成功）==")
    for name in _list_corpus(clean_dir, exts):
        n_clean += 1
        with open(os.path.join(clean_dir, name), encoding="utf-8") as f:
            src = f.read()
        try:
            r = _fmt(src, args.pack)
        except Exception as exc:
            failures.append(f"[CRASH] clean/{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL {name}: crash")
            continue
        if not r.get("success"):
            failures.append(f"[CLEAN-FAIL] clean/{name}: {r.get('error')}")
            print(f"  FAIL {name}: {r.get('error')}")
            continue
        bad = _kind_violation(src, args.pack, name, failures)
        print(f"  ok   {name}" + (f"（并守住 {bad}）" if bad else ""))

    print("== reject（必须失败且不崩溃）==")
    for name in _list_corpus(reject_dir, exts):
        n_reject += 1
        with open(os.path.join(reject_dir, name), encoding="utf-8") as f:
            src = f.read()
        try:
            r = _fmt(src, args.pack)
        except Exception as exc:
            failures.append(f"[CRASH] reject/{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL {name}: crash")
            continue
        if r.get("success"):
            failures.append(f"[REJECT-PASSED] reject/{name}: 本应失败却成功")
            print(f"  FAIL {name}: 应失败却成功")
        else:
            bad = _kind_violation(src, args.pack, name, failures)
            print(f"  ok   {name} ({r.get('error', '')[:60]})"
                  + (f"（并守住 {bad}）" if bad else ""))

    print(f"\nclean: {n_clean}  reject: {n_reject}  failures: {len(failures)}")
    if failures:
        for f_ in failures:
            print("  " + f_)
        sys.exit(1)
    print("OK — edge corpus behaves as expected")


if __name__ == "__main__":
    main()
