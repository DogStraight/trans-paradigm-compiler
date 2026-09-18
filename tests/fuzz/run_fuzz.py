"""run_fuzz.py — fuzz 主循环：生成/变异输入 → 管线 → 断言不变量。

不变量（oracle）：
    - 不崩溃：任何输入不得抛异常（软失败可，崩溃不行）。
    - token 保序：格式化前后非 trivia token 序列必须一致（可改排版，不可改内容）。
    - 幂等：format(format(x)) == format(x)（preserve 路径的既有保证）。
    - 成功 → 输出可再解析（成功即管线内 round-trip）。

失败输入保存到 findings/ 供最小化后沉淀进 edge 语料。退出码：有违反=1。

用法：
    python tests/fuzz/run_fuzz.py --iters 500 --seed 42
    python tests/fuzz/run_fuzz.py --mutate-only   # 只跑变异，不跑语法生成

Doc: tests/fuzz/README.md
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

# 仓库根引导（脚本从 tests/fuzz/ 运行时保证 import 可用）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from core.token_protocol import TRIVIA_TOKEN_TYPES
from lexer import Lexer

from generate import (
    GrammarFuzzer,
    collect_seeds,
    mutate_source,
    build_token_map,
)

DEFAULT_RULES_DIR = "grammar/verilog"
_FINDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "findings")


def _fmt(source: str) -> dict:
    """按 format 指令的管线设置运行（与 main.py format 同参）。"""
    from pipeline import run_pipeline_on_source

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


def _token_seq(text: str, lexer: Lexer):
    try:
        toks = lexer.tokenize(text)
    except Exception:
        # 不能 token 化 → 返回 None 由调用方判定（不在这里报错：调用方分
        # "输入本来就不可 token 化"（语料本就可能坏）与"输出不可 token 化"
        # （真缺陷）两种情形，不能一律当通过）
        return None
    return [(t.type, t.content) for t in toks if t.type not in TRIVIA_TOKEN_TYPES]


def check_one(src: str, lexer: Lexer, findings: list, label: str,
              index: int, findings_dir: str) -> None:
    """对单个输入跑全部不变量；违反则记录。"""
    try:
        r = _fmt(src)
    except Exception as exc:  # 崩溃 = 违反
        _save(findings_dir, f"{index:05d}_crash_{label}.v", src)
        findings.append(f"[CRASH] {label}: {type(exc).__name__}: {exc}")
        return

    if not r.get("success"):
        # 软失败：要求有 error 信息（静默失败也算异常）
        if not r.get("error"):
            _save(findings_dir, f"{index:05d}_silent_{label}.v", src)
            findings.append(f"[SILENT-FAIL] {label}: success=False 且无 error")
        return

    out = r.get("output", "")
    if not out:
        return

    # token 保序（仅对语法驱动生成的合法程序断言——格式化契约是"合法输入
    # 不改内容"。mutation 产物多为畸形：容错解析路径（补分号/重构结构）会
    # 合法地改变 token 序列，不变量在那里不成立；宏指令路径同理已排除）
    if label == "gen" and not any(
        marker in src
        for marker in ("`ifdef", "`ifndef", "`define", "`include",
                       "`else", "`elsif", "`endif", "`timescale",
                       "`resetall", "`celldefine")
    ):
        seq_in = _token_seq(src, lexer)
        seq_out = _token_seq(out, lexer)
        if seq_in is not None and seq_out is None:
            # 输入可 token 化、输出却不可 → 格式化把输出弄成不可 token 化（真缺陷），
            # 不能因"有一侧为 None"就把整条不变量静默跳过。
            _save(findings_dir, f"{index:05d}_tokenizefail_{label}.v", src)
            findings.append(f"[TOKENIZE-FAIL] {label}: 格式化输出无法 token 化")
        elif seq_in is not None and seq_out is not None and seq_in != seq_out:
            _save(findings_dir, f"{index:05d}_tokencorrupt_{label}.v", src)
            findings.append(
                f"[TOKEN-CORRUPT] {label}: 格式化改变了 token 序列 "
                f"(in {len(seq_in)} → out {len(seq_out)} tokens)"
            )

    # 幂等
    try:
        r2 = _fmt(out)
    except Exception as exc:
        _save(findings_dir, f"{index:05d}_idem_crash_{label}.v", src)
        findings.append(f"[IDEM-CRASH] {label}: 二次格式化崩溃: {exc}")
        return
    if r2.get("success") and r2.get("output") != out:
        _save(findings_dir, f"{index:05d}_nonidem_{label}.v", src)
        findings.append(f"[NON-IDEMPOTENT] {label}: format(format(x)) != format(x)")


def _save(findings_dir: str, name: str, src: str) -> None:
    # Windows 文件名限制：label 里可能含 ':' 等非法字符 → 消毒
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    os.makedirs(findings_dir, exist_ok=True)
    try:
        with open(os.path.join(findings_dir, safe), "w", encoding="utf-8") as f:
            f.write(src)
    except OSError as exc:
        print(f"  [warn] 无法保存 finding {safe}: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description="tpc formatter fuzz harness")
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mutate-only", action="store_true",
                    help="只跑变异（跳过语法驱动生成）")
    ap.add_argument("--rules-dir", default=DEFAULT_RULES_DIR)
    ap.add_argument("--findings-dir", default=_FINDINGS_DIR)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rules_dir = args.rules_dir
    lexer = Lexer(rules_dir=rules_dir)
    token_map = build_token_map(rules_dir)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    seeds = collect_seeds(
        os.path.join(repo_root, "tests", "e2e", "samples"),
        os.path.join(repo_root, "tests", "edge", "edge_corpus"),
    )
    print(f"seeds: {len(seeds)} files")

    fuzzer = None if args.mutate_only else GrammarFuzzer(rules_dir, rng)
    findings: list[str] = []
    t0 = time.time()
    n_crash = 0

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
            src = mutate_source(seed_src, rng, token_map, rules_dir)
            label = f"mut:{os.path.basename(seed)}"
        before = len(findings)
        check_one(src, lexer, findings, label, i, args.findings_dir)
        if len(findings) > before:
            n_crash += 1

    dt = time.time() - t0
    print(f"iterations: {args.iters}  findings: {len(findings)}  "
          f"elapsed: {dt:.1f}s ({args.iters / dt:.0f} iter/s)")
    for f in findings[:20]:
        print("  " + f)
    if findings:
        print(f"FAIL — findings saved to {args.findings_dir}")
        sys.exit(1)
    print("OK — no invariant violations")


if __name__ == "__main__":
    main()
