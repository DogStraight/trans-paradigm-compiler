"""run_fuzz.py — fuzz 主循环：生成/变异输入 → 管线 → 断言不变量。

不变量（oracle）定义在 `oracle.py`（**单一来源**：最小化/沉淀必须用同一份判据）；
本文件只负责"生成输入 → 跑判据 → 记录现场"。

失败输入保存到 findings/（gitignored），并写一份机器可读索引 `index.jsonl`
供 `shrink.py` 直接消费（类别 + 标签 + 目标语言包——最小化要复现同一个违反，
少了这三样就得靠猜）。退出码：有违反=1。

语言包：`--pack` 同时决定**生成器 / 词法 / 管线 / 种子**（此前 `--rules-dir`
只作用于前两者，管线恒用默认包 ⇒ 换个包跑出来的 finding 全是假的）。
非默认包默认取该包自己的样本作种子（`tests/languages/<name>/samples`）。

用法：
    python tests/fuzz/run_fuzz.py --iters 500 --seed 42
    python tests/fuzz/run_fuzz.py --mutate-only            # 只跑变异
    python tests/fuzz/run_fuzz.py --pack grammar/c --iters 500

Doc: tests/fuzz/README.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

# 仓库根引导（脚本从 tests/fuzz/ 运行时保证 import 可用）
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
sys.path.insert(0, _HERE)

from lexer import Lexer  # noqa: E402

import oracle  # noqa: E402
from generate import (  # noqa: E402
    GrammarFuzzer,
    build_token_map,
    collect_seeds,
    mutate_source,
)

DEFAULT_RULES_DIR = "grammar/verilog"
DEFAULT_SEED_ROOTS: tuple[str, ...] = ("tests/e2e/samples", "tests/edge/edge_corpus")
_INDEX_NAME = "index.jsonl"
# 各语言包的样本后缀（种子收集用）
_SEED_EXTS: dict[str, tuple[str, ...]] = {
    "grammar/c": (".c", ".h"),
    "grammar/c4": (".c",),
}


def _save(findings_dir: str, name: str, src: str) -> str:
    """落盘失败输入，返回文件名（Windows 文件名限制：非法字符消毒）。"""
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    os.makedirs(findings_dir, exist_ok=True)
    try:
        with open(os.path.join(findings_dir, safe), "w", encoding="utf-8") as f:
            f.write(src)
    except OSError as exc:
        print(f"  [warn] 无法保存 finding {safe}: {exc}")
    return safe


def _append_index(findings_dir: str, rec: dict) -> None:
    """findings 索引（jsonl，一行一条）：shrink 的输入。"""
    os.makedirs(findings_dir, exist_ok=True)
    with open(os.path.join(findings_dir, _INDEX_NAME), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def seed_roots_for(pack: str) -> tuple[str, ...]:
    """种子目录：默认（e2e 样本 + edge 语料）+ 非默认包自己的样本目录。"""
    roots = list(DEFAULT_SEED_ROOTS)
    if pack != DEFAULT_RULES_DIR:
        name = os.path.basename(os.path.normpath(pack))
        roots.append(os.path.join("tests", "languages", name, "samples"))
    return tuple(roots)


def check_one(src: str, lexer: Lexer, findings: list, label: str,
              index: int, findings_dir: str, pack: str,
              ext_dirs: list[str], write_index: bool = True) -> None:
    """对单个输入跑全部不变量；违反则记录（现场 + 索引）。"""
    violations = oracle.evaluate_format(
        src, lexer, rules_dir=pack, ext_dirs=ext_dirs, label=label
    )
    for v in violations:
        fname = _save(findings_dir, f"{index:05d}_{v.kind}_{label}.v", src)
        findings.append(f"{v} [{label}]")
        if write_index:
            _append_index(
                findings_dir,
                {
                    "file": fname,
                    "kind": v.kind,
                    "detail": v.detail,
                    "label": label,
                    "pack": pack,
                    "iteration": index,
                },
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="tpc formatter fuzz harness")
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mutate-only", action="store_true",
                    help="只跑变异（跳过语法驱动生成）")
    ap.add_argument("--pack", "--rules-dir", dest="pack", default=DEFAULT_RULES_DIR,
                    help="目标语言包（生成器 / 词法 / 管线 / 种子同参）")
    ap.add_argument("--seed-root", action="append", default=None,
                    help="种子目录（可重复；默认 e2e 样本 + edge 语料）")
    ap.add_argument("--findings-dir", default=os.path.join(_HERE, "findings"))
    ap.add_argument("--no-index", action="store_true",
                    help="不写 findings/index.jsonl（临时探查用）")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    pack = args.pack
    ext_dirs = oracle.ext_dirs_for(pack)
    lexer = Lexer(rules_dir=pack, ext_dirs=ext_dirs)
    token_map = build_token_map(pack)

    roots = args.seed_root if args.seed_root else seed_roots_for(pack)
    exts = _SEED_EXTS.get(pack, (".v",))
    seeds = collect_seeds(*(os.path.join(_REPO, r) for r in roots), extensions=exts)
    print(f"pack: {pack}  seeds: {len(seeds)} files")

    fuzzer = None if args.mutate_only else GrammarFuzzer(pack, rng, ext_dirs=ext_dirs)
    findings: list[str] = []
    t0 = time.time()

    for i in range(args.iters):
        if fuzzer is not None and rng.random() < 0.3:
            src = fuzzer.generate()
            label = "gen"
        else:
            if not seeds:
                print("no seeds; add corpus files or drop --mutate-only")
                sys.exit(2)
            seed = rng.choice(seeds)
            with open(seed, "r", encoding="utf-8", errors="replace") as f:
                seed_src = f.read()
            src = mutate_source(seed_src, rng, token_map, pack, ext_dirs=ext_dirs)
            label = f"mut:{os.path.basename(seed)}"
        check_one(src, lexer, findings, label, i, args.findings_dir, pack, ext_dirs,
                  write_index=not args.no_index)

    dt = time.time() - t0
    print(f"iterations: {args.iters}  findings: {len(findings)}  "
          f"elapsed: {dt:.1f}s ({args.iters / dt:.0f} iter/s)")
    for f in findings[:20]:
        print("  " + f)
    if findings:
        print(f"FAIL — findings saved to {args.findings_dir}")
        print("  下一步：python tests/fuzz/shrink.py --all "
              f"--pack {pack}   # 最小化（+ --sediment 沉淀）")
        sys.exit(1)
    print("OK — no invariant violations")


if __name__ == "__main__":
    main()
