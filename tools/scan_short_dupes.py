"""scan_short_dupes.py — 短重复扫描：函数体级 token 相似度（**含 tools/ 与 policy/ 自身**）。

**为什么有它**（2026-11-07 审计）：`structural_score` 的 CLONE 判据是 token 阈值，
10–20 行的整段复制掉在盲区——实测 tools 层因此长出 3 个"遍历仓库 py 文件"实现
（相似度 0.14/0.24/0.47）、2 份 `_record_skipped_input`（0.90）。**门禁有盲区，
债就长在盲区里**，而且长在工具自己身上。

判据：把每个函数体归一化成 token 序列（标识符→N、字符串→S、数字→NUM、去 docstring），
两两比对相似度；`≥ --min-ratio`（默认 0.85）且 token 数 `≥ --min-tokens`（默认 40）
即报。工具目录与产品目录**同权扫描**——工具不豁免自己。

只报告，不做裁决：重复要不要合并由人判（同形不同源是合法结论）。
`--strict` 时发现即 exit 1；默认 exit 0（report-only）。
"""
from __future__ import annotations

import argparse
import ast
import difflib
import io
import json
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PY_FILES = 200
SKIP_DIRS = frozenset({
    ".git", "dist", "build", "_drafts", ".scratch", ".agents", "__pycache__",
    ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
})
SKIPPED_INPUTS: list[tuple[str, str]] = []


@dataclass(frozen=True)
class Unit:
    """一个函数体的归一化 token 序列。"""
    path: str
    line: int
    name: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class Pair:
    """一对相似函数。"""
    ratio: float
    a: Unit
    b: Unit


def _record(rel: str, reason: str) -> None:
    if (rel, reason) not in SKIPPED_INPUTS:
        SKIPPED_INPUTS.append((rel, reason))


def _iter_py_files(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            _record(str(root), "输入根不存在")
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            out.append(path)
    return out


def _normalize(body: ast.AST) -> tuple[str, ...]:
    """函数体的 token 归一化序列（标识符/字符串/数字抽象掉，去 docstring）。"""
    text = ast.unparse(body)
    toks: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                            tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
                continue
            if tok.type == tokenize.NAME:
                # **保留标识符**：全抽象成 N 会把"任何循环"都变成同一份（实测 0.85 阈值下
                # 一次报出 567 对，全是噪声）。名字带语义，是区分"同形不同源"的关键信号。
                toks.append(tok.string)
            elif tok.type == tokenize.STRING:
                toks.append("S")
            elif tok.type == tokenize.NUMBER:
                toks.append("NUM")
            else:
                toks.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return ()
    return tuple(toks)


def _units(path: Path) -> list[Unit]:
    rel = path.relative_to(ROOT).as_posix() if ROOT in path.parents else str(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        _record(rel, f"解析失败：{type(exc).__name__}")
        return []
    out: list[Unit] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [stmt for stmt in node.body
                if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str))]
        if not body:
            continue
        toks = _normalize(ast.Module(body=body, type_ignores=[]))
        if toks:
            out.append(Unit(rel, node.lineno, node.name, toks))
    return out


def _candidates(big: list[Unit], k: int = 4, shared: int = 4) -> set[tuple[int, int]]:
    """用小 k-gram 倒排索引挑候选对（避免 O(n^2) 的 SequenceMatcher 全量比对）。"""
    index: dict[tuple[str, ...], list[int]] = {}
    for idx, unit in enumerate(big):
        grams = {unit.tokens[i:i + k] for i in range(len(unit.tokens) - k + 1)}
        for gram in grams:
            index.setdefault(gram, []).append(idx)
    hits: dict[tuple[int, int], int] = {}
    for idxs in index.values():
        if len(idxs) < 2 or len(idxs) > 40:   # 太常见的 k-gram（`N . N (` 之类）无区分力
            continue
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                key = (idxs[i], idxs[j])
                hits[key] = hits.get(key, 0) + 1
    return {key for key, count in hits.items() if count >= shared}


def scan(roots: list[Path], min_ratio: float, min_tokens: int) -> list[Pair]:
    """扫描并返回相似函数对（按相似度降序）。"""
    del SKIPPED_INPUTS[:]
    units: list[Unit] = []
    for path in _iter_py_files(roots):
        units.extend(_units(path))
    big = [u for u in units if len(u.tokens) >= min_tokens]
    pairs: list[Pair] = []
    for i, j in sorted(_candidates(big)):
        a, b = big[i], big[j]
        ratio = difflib.SequenceMatcher(None, a.tokens, b.tokens).ratio()
        if ratio >= min_ratio:
            pairs.append(Pair(ratio, a, b))
    pairs.sort(key=lambda p: -p.ratio)
    return pairs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scan_short_dupes", description=__doc__.splitlines()[0])
    ap.add_argument("--paths", default=None, help="逗号分隔的扫描根（默认仓库根）")
    ap.add_argument("--min-ratio", type=float, default=0.90)
    ap.add_argument("--min-tokens", type=int, default=60)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--strict", action="store_true", help="发现即 exit 1")
    args = ap.parse_args(argv)
    roots = [Path(p) for p in args.paths.split(",")] if args.paths else [ROOT]
    pairs = scan(roots, args.min_ratio, args.min_tokens)
    for p in pairs:
        print(f"  {p.ratio:.2f}  {p.a.path}:{p.a.line} {p.a.name}  <->  {p.b.path}:{p.b.line} {p.b.name}")
    print(f"\n[scan_short_dupes] {len(pairs)} 对相似函数（阈值 {args.min_ratio:.2f} / {args.min_tokens} tok）")
    if args.json:
        args.json.write_text(json.dumps(
            [{"ratio": round(p.ratio, 3), "a": [p.a.path, p.a.line, p.a.name],
              "b": [p.b.path, p.b.line, p.b.name]} for p in pairs], ensure_ascii=False, indent=2),
            encoding="utf-8")
    return 1 if (args.strict and pairs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
