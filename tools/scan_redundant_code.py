"""scan_redundant_code.py — 逐部件冗余代码扫描（**最小形式**的机械部分，只报告）。

**为什么有它**（2026-11-07 D10 维度）：冗余代码审查此前靠人读，逐部件、易漏。
可机械判定的只有三类，本工具只做这三类，其余（同义重复、过度分层）留给人判：

- R1 **零引用定义**：全仓 `git grep -w <name>` 只命中定义处（协议方法 `__x__` 排除）
- R2 **未使用参数**：函数体内从未出现的形参（`self`/`cls`/`*args`/`**kwargs` 排除）
- R3 **纯转发包装**：函数体只有 `return other(same args)`，且无校验/转换/日志等额外语义

只报告，不裁决：**"删不删"由人判**（含"抽象分层不许破坏"这条更高优先的约束）。
`--strict` 时发现即 exit 1。
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PY_FILES = 20
SKIP_DIRS = frozenset({
    ".git", "dist", "build", "_drafts", ".scratch", ".agents", "__pycache__",
    ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
})
SKIPPED_INPUTS: list[tuple[str, str]] = []


@dataclass(frozen=True)
class Finding:
    """一条冗余候选。"""
    path: str
    line: int
    code: str
    name: str
    detail: str


def _record(rel: str, reason: str) -> None:
    if (rel, reason) not in SKIPPED_INPUTS:
        SKIPPED_INPUTS.append((rel, reason))


def _git_grep_hits(name: str) -> int:
    """全仓（.py/.toml/.md）里该标识符命中的行数。"""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "grep", "-w", name, "--", "*.py", "*.toml", "*.md"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return len([ln for ln in proc.stdout.splitlines() if ln.strip()])


def _unused_args(node: ast.AST, args: list[ast.arg]) -> list[str]:
    """函数体内从未出现的形参名。"""
    used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    return [a.arg for a in args
            if a.arg not in ("self", "cls") and a.arg not in used]


def _passthrough_target(node: ast.AST, args: list[ast.arg]) -> str | None:
    """纯转发：body 只有一个 `return f(同名参数...)` → 返回被调名。"""
    body = [s for s in getattr(node, "body", [])
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return None
    call = body[0].value
    if not isinstance(call, ast.Call):
        return None
    names = [a.arg for a in args]
    passed = [a.id for a in call.args if isinstance(a, ast.Name)]
    if not names or set(passed) != set(names):
        return None
    func = call.func
    return getattr(func, "id", None) or getattr(func, "attr", None)


def scan_file(path: Path) -> list[Finding]:
    """单文件 → 候选列表。"""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError) as exc:
        _record(path.as_posix(), f"解析失败：{type(exc).__name__}")
        return []
    rel = path.relative_to(ROOT).as_posix() if ROOT in path.parents else str(path)
    out: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = list(node.args.args) + list(node.args.kwonlyargs)
        name = node.name
        if name.startswith("_") and not (name.startswith("__") and name.endswith("__")):
            if _git_grep_hits(name) <= 1:
                out.append(Finding(rel, node.lineno, "R1", name, "零引用（全仓仅定义处）"))
        unused = _unused_args(node, args)
        if unused:
            out.append(Finding(rel, node.lineno, "R2", name, f"未使用形参 {unused}"))
        target = _passthrough_target(node, args)
        if target:
            out.append(Finding(rel, node.lineno, "R3", name, f"纯转发到 {target}()"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scan_redundant_code", description=__doc__.splitlines()[0])
    ap.add_argument("--paths", default=None, help="逗号分隔的部件目录（默认 linter,parser）")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--strict", action="store_true", help="发现即 exit 1")
    args = ap.parse_args(argv)
    roots = [Path(p) for p in (args.paths or "linter,parser").split(",")]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            _record(str(root), "输入根不存在")
            continue
        files.extend(p for p in sorted(root.rglob("*.py"))
                     if not any(part in SKIP_DIRS for part in p.parts))
    findings: list[Finding] = []
    for path in files:
        findings.extend(scan_file(path))
    for f in findings:
        print(f"  {f.path}:{f.line} {f.code} {f.name}: {f.detail}")
    print(f"\n[scan_redundant_code] {len(files)} 文件 / {len(findings)} 条候选"
          f"（R1 零引用 / R2 未使用参数 / R3 纯转发）")
    if args.json:
        args.json.write_text(json.dumps([f.__dict__ for f in findings], ensure_ascii=False, indent=2),
                             encoding="utf-8")
    if len(files) < MIN_PY_FILES:
        print(f"[FAIL] 扫描面不足：{len(files)} 文件 < 下限 {MIN_PY_FILES}")
        return 2
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
