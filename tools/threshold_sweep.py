#!/usr/bin/env python3
"""threshold_sweep.py — 通用数值旋钮 sweep 量具（只出原始表，不出结论）。

为什么有它（审计 2026-11-05，作者批）：增量闸门 `parser/incremental.py` 的
20–30% 阈值是**估算**。要把"估算"升级为"测量"，但量具本身必须**通用 + 有外部性**：

- **普适性**：接收"任意数值旋钮 + 任意语料/重跑器 + 任意目标量"，输出
  `旋钮取值 → 目标量（多轮原始值 + 中位数 + 极差）`；换旋钮（如 `_MAX_JOINED_LINES`、
  并发 worker 数）不改编排代码 ⇒ 用 `--runner module:func` 注入。
- **外部性**：
  - 本工具**只打印/保存原始数字**，不输出"阈值应该设为 X"这类判断（判断归作者）；
  - 语料与调参语料分离由调用方保证（工具不读训练集；builtin 只用评估语料）；
  - 一条命令可复跑；同输入同结果（确定性 runner 无随机；重复次数用于看离散度）。
- **免假绿**：`--selftest` 用合成旋钮/重跑器证明"旋钮变化 ⇒ 表跟着变"，否则量具
  可能空转。

用法：
    python tools/threshold_sweep.py --selftest
    python tools/threshold_sweep.py --incremental                 # 增量闸门评估（真实语料）
    python tools/threshold_sweep.py --incremental --save tools/baselines/incremental_threshold_sweep.json
    python tools/threshold_sweep.py --runner mymod:fn --points 1,2,4 --repeats 3

通用接口契约（`--runner`）：`fn(knob: float) -> float`，返回该旋钮取值下的目标量
（秒 / 字节 / 计数均可，单位由 runner 自己负责）。
"""

from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.console import ensure_utf8_stdio  # noqa: E402 — 路径引导之后才可 import

ensure_utf8_stdio()

_DEFAULT_POINTS = "0.02,0.05,0.10,0.20,0.30,0.45"
_DEFAULT_CORPUS = "tests/e2e/samples/real/ref/ref_tv80_core.v"


@dataclass
class SweepRow:
    """一行原始表：旋钮取值 + 多轮目标量（不解释、不建议）。"""

    knob: float
    values: list[float]

    @property
    def median(self) -> float:
        return statistics.median(self.values)

    @property
    def spread(self) -> float:
        return max(self.values) - min(self.values)


def sweep(points: list[float], runner, repeats: int) -> list[SweepRow]:
    """对每个旋钮取值跑 `repeats` 轮，返回原始表（无结论）。"""
    return [
        SweepRow(knob=p, values=[float(runner(p)) for _ in range(max(1, repeats))])
        for p in points
    ]


def _selftest() -> int:
    """合成自检：knob 变化 ⇒ 表变化；round 数生效；无结论输出。"""
    points = [1.0, 2.0, 4.0]
    rows = sweep(points, lambda k: k * 10.0, repeats=2)
    medians = [r.median for r in rows]
    ok = medians == [10.0, 20.0, 40.0] and all(len(r.values) == 2 for r in rows)
    # 反向自检：坏 runner（不随旋钮变）必须能被如实识别为"不敏感"
    flat = sweep(points, lambda _k: 7.0, repeats=1)
    flat_detected = len({r.median for r in flat}) == 1
    print("[selftest] knob→value 表随旋钮变化:", "PASS" if ok else "FAIL", medians)
    print("[selftest] 常量 runner 被如实识别为不敏感:", "PASS" if flat_detected else "FAIL")
    return 0 if (ok and flat_detected) else 1


def _load_runner(spec: str):
    """`module:func` → 可调用 runner（模块从仓库根/当前 sys.path 解析）。"""
    module_name, _, func_name = spec.partition(":")
    if not module_name or not func_name:
        raise SystemExit(f"--runner 需为 'module:function' 形态，实得 {spec!r}")
    fn = getattr(importlib.import_module(module_name), func_name)
    if not callable(fn):
        raise SystemExit(f"--runner 目标不可调用：{spec!r}")
    return fn


# ── builtin：增量闸门评估（真实语料；测"片段解析成本代理 vs 全量解析成本"）──


def _load_v_parser(rules: str = "grammar/verilog"):
    """真实语料同款装配（与 check 同路：宏展开 → 词法 → 语法）。"""
    from analyzer.shared_components import SharedComponents
    from parser import Parser

    shared = SharedComponents.get(rules, [], None)
    return (
        shared["lexer"],
        Parser(
            rules_dir=rules,
            rules=shared["rules"],
            rule_selector=shared["rule_selector"],
        ),
    )


def _expand_source(source: str, rules: str = "grammar/verilog") -> str:
    """与 check 同路的宏展开（tv80 原文含 `define，不能直接 parse）。"""
    from preprocessor import expand_tokens, scan_directives

    events: list = []
    macro_table, func_macros, _, _, _, clean, clean_to_raw = scan_directives(
        source, rules, search_dirs=[], out_macro_events=events
    )
    if macro_table:
        clean, _, _, _ = expand_tokens(
            clean,
            macro_table,
            rules_dir=rules,
            func_macros=func_macros,
            events=events,
            clean_to_raw=clean_to_raw,
        )
    return clean


def _units_with_span(ast) -> list[tuple[int, int, str]]:
    """顶层单元 `(start, end, rule)`（只收带 `_tok_span` 的节点）。"""
    units: list[tuple[int, int, str]] = []
    for child in getattr(ast, "sub_node", []) or []:
        span = getattr(child, "_tok_span", None)
        if isinstance(span, tuple) and len(span) == 2 and span[0] < span[1]:
            units.append((span[0], span[1], child.node_name))
    return units


def _rename_identifier(tokens: list, start: int, end: int):
    """单元内挑一个标识符改成合法新名 → `(下标, 新 Token)`；无可用 token → None。"""
    from core.define import Token

    for i in range(start + 3, end - 3):
        tok = tokens[i]
        if tok.type.startswith("id") and tok.content:
            return i, Token(
                content=f"{tok.content}_sweep",
                type=tok.type,
                line=tok.line,
                column=tok.column,
            )
    return None


def _measure_one(parser, tokens: list, start: int, end: int, rule: str, repeats: int):
    """单个占比点：多轮测全量 parse 与片段 parse（只计时调用本身）。"""
    edit = _rename_identifier(tokens, start, end)
    if edit is None:
        return None
    index, new_token = edit
    new_tokens = list(tokens)
    new_tokens[index] = new_token
    full_times: list[float] = []
    frag_times: list[float] = []
    for _ in range(max(1, repeats)):
        t0 = time.perf_counter()
        parser.parse(new_tokens)
        full_times.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        parser.parse_fragment(new_tokens[start:end], rule)
        frag_times.append(time.perf_counter() - t0)
    return full_times, frag_times


def _row_for_point(
    parser, tokens: list, units: list, total: int, target: float, repeats: int
) -> dict:
    """一个目标占比点 → 原始表行（实际占比如实记录，不假装精确命中）。"""
    start, end, rule = min(units, key=lambda u: abs((u[1] - u[0]) / total - target))
    ratio = (end - start) / total
    measured = _measure_one(parser, tokens, start, end, rule, repeats)
    if measured is None:
        return {"target_ratio": target, "actual_ratio": ratio, "note": "no-id-token"}
    full_times, frag_times = measured
    full_ms = statistics.median(full_times) * 1000
    frag_ms = statistics.median(frag_times) * 1000
    return {
        "target_ratio": target,
        "actual_ratio": round(ratio, 4),
        "unit": rule,
        "frag_tokens": end - start,
        "total_tokens": total,
        "full_ms": round(full_ms, 2),
        "frag_ms": round(frag_ms, 2),
        "speedup": round(full_ms / frag_ms, 2) if frag_ms else None,
        "full_all_ms": [round(v * 1000, 2) for v in full_times],
        "frag_all_ms": [round(v * 1000, 2) for v in frag_times],
    }


def _incremental_sweep(
    corpus: str, points: list[float], repeats: int, save: str | None
) -> list[dict]:
    """增量闸门原始表：目标片段占比 → 片段解析/全量解析耗时（多轮中位数）。

    口径：旋钮 = 目标片段占比（片段 token / 全量 token），取最近的真实顶层单元并
    记录**实际占比**；片段耗时 = `Parser.parse_fragment`（增量成本代理，绕过闸门），
    全量耗时 = `Parser.parse`。只出原始表，不写"阈值该设多少"。
    """
    lexer, parser = _load_v_parser()
    expanded = _expand_source(Path(corpus).read_text(encoding="utf-8"))
    tokens = lexer.tokenize(expanded)
    ast = parser.parse(tokens)
    if ast is None or getattr(parser, "_parse_truncated", False):
        raise SystemExit(f"语料解析失败：{corpus}")
    units = _units_with_span(ast)
    if not units:
        raise SystemExit("语料没有带 span 的顶层单元（无法 sweep）")
    rows = [
        _row_for_point(parser, tokens, units, len(tokens), target, repeats)
        for target in points
    ]
    if save:
        Path(save).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[info] 原始表已写入 {save}")
    return rows


def _print_incremental(rows: list[dict]) -> None:
    """原始表（列名即口径；不输出结论）。"""
    print("target_ratio actual_ratio unit frag_tokens/total full_ms frag_ms speedup")
    for r in rows:
        if "note" in r:
            print(f"{r['target_ratio']:.2f} {r['actual_ratio']:.4f} {r['note']}")
            continue
        print(
            f"{r['target_ratio']:.2f} {r['actual_ratio']:.4f} {r['unit']} "
            f"{r['frag_tokens']}/{r['total_tokens']} {r['full_ms']:.2f} "
            f"{r['frag_ms']:.2f} {r['speedup']}"
        )


def _cmd_incremental(args: argparse.Namespace, points: list[float]) -> int:
    rows = _incremental_sweep(args.corpus, points, args.repeats, args.save)
    _print_incremental(rows)
    return 0


def _cmd_generic(args: argparse.Namespace, points: list[float]) -> int:
    if not args.runner:
        raise SystemExit("通用模式需 --runner module:function（或 --incremental / --selftest）")
    rows = sweep(points, _load_runner(args.runner), args.repeats)
    if args.save:
        Path(args.save).write_text(
            json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[info] 原始表已写入 {args.save}")
    print("knob median spread values")
    for r in rows:
        print(f"{r.knob:.4f} {r.median:.4f} {r.spread:.4f} {r.values}")
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="threshold_sweep",
        description="通用数值旋钮 sweep 量具：只出原始表，不出结论（阈值判断归作者）",
    )
    ap.add_argument("--selftest", action="store_true", help="合成自检：表随旋钮变化")
    ap.add_argument("--incremental", action="store_true", help="builtin：增量闸门评估（真实语料）")
    ap.add_argument("--corpus", default=_DEFAULT_CORPUS, help="builtin 评估语料（默认 tv80）")
    ap.add_argument("--points", default=_DEFAULT_POINTS, help="旋钮取值列表（逗号分隔）")
    ap.add_argument("--repeats", type=int, default=3, help="每个取值重复轮数（看离散度）")
    ap.add_argument("--runner", default=None, help="通用模式：module:function（knob→value）")
    ap.add_argument("--save", default=None, help="把原始表 JSON 写到该路径")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    points = [float(p) for p in args.points.split(",") if p.strip()]
    return _cmd_incremental(args, points) if args.incremental else _cmd_generic(args, points)


if __name__ == "__main__":
    raise SystemExit(main())
