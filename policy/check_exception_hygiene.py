"""check_exception_hygiene.py — 异常卫生门禁（模型高频缺陷：吞异常）。

**为什么有这条**（2026-11-07 审计）：模型为了让测试不崩，最常见的动作是
`except Exception: pass` / `return None`——错误就此消失，不报错、不红、只表现为
"某功能不生效"。本仓策略从来不是"禁止宽异常"，而是**宽异常必须写明理由**，
这与既有写法一致（代码里已有 `# noqa: BLE001 — <理由>` 惯例，本门禁把它变成判据）。

判据（两条，均可机械判定）：
- H1 宽异常（`except Exception` / `except BaseException`）必须带
  `# noqa: BLE001 — <非空理由>`；理由为空或缺失 → 红。
- H2 裸 `except:` → 红（它连"抓的是什么"都没说）。

**不判什么**：不判断"这个 except 该不该存在"（那是人判）。本门禁只保证：
凡宽异常，写的人必须当场说明为什么宽。

退出码：0 干净；1 有 H1/H2 或 ALLOW 腐化；2 输入面缺失 / `--strict` 下的解析失败 /
扫描文件数低于下限（防假绿）。

用法::

    python policy/check_exception_hygiene.py
    python policy/check_exception_hygiene.py --selftest
    python policy/check_exception_hygiene.py --json out.json --strict
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

# Windows 控制台/管道默认编码（GBK/cp1252）编不了中文：本进程自护 stdout/stderr。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent
MIN_PY_FILES = 200
CODES = ("H1", "H2")
NOQA_RE = re.compile(r"noqa:\s*BLE001\s*(?:—|-|:)\s*(?P<reason>\S.*)$")
SKIP_DIRS = frozenset({
    ".git", "dist", "build", "_drafts", ".scratch", ".agents", "__pycache__", ".venv",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
})
#: 允许清单：`相对路径:码` → 理由。条目一次都没命中即视为腐化（E-ALLOW-STALE）。
ALLOW: dict[str, str] = {}

SKIPPED_INPUTS: list[tuple[str, str]] = []


@dataclass
class Finding:
    """一条违规。"""
    path: str
    line: int
    code: str
    message: str


@dataclass
class Report:
    """一次扫描的结果。"""
    scanned_files: int = 0
    findings: list[Finding] = field(default_factory=list)
    skipped_inputs: list[tuple[str, str]] = field(default_factory=list)
    stale_allows: list[str] = field(default_factory=list)

    @property
    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


def _record_skipped(rel: str, reason: str) -> None:
    if (rel, reason) not in SKIPPED_INPUTS:
        SKIPPED_INPUTS.append((rel, reason))


def _iter_py_files(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            _record_skipped(str(root), "输入根不存在")
            continue
        if root.is_file() and root.suffix == ".py":
            out.append(root)
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(ROOT).parts if ROOT in path.parents else path.parts
            if any(part in SKIP_DIRS for part in rel):
                continue
            out.append(path)
    return out


def _noqa_reason(line: str) -> str | None:
    """该行 `# noqa: BLE001 — 理由` 里的理由；无注释或无理由 → None。"""
    match = NOQA_RE.search(line)
    return match.group("reason").strip() if match else None


def _except_line(source_lines: list[str], node: ast.ExceptHandler) -> str:
    """`except` 那一行本身。

    ⚠ 只认**同一行**的 `# noqa`：早期实现把整个 handler 块拼成多行再正则，结果
    `\\s*` 跨了换行，把**下一行代码**当成了"理由"（实测：`# noqa: BLE001 -` 后面跟
    `pass` 时理由被读成 `pass`，而真正写了理由的那行反倒被判红）。一行一判，不留这个坑。
    """
    index = node.lineno - 1
    return source_lines[index] if 0 <= index < len(source_lines) else ""


def _scan_tree(tree: ast.Module, rel: str, source: str) -> list[Finding]:
    lines = source.splitlines()
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        reason = _noqa_reason(_except_line(lines, node))
        if node.type is None:
            findings.append(Finding(rel, node.lineno, "H2", "裸 except（连抓什么都没说）"))
            continue
        broad = _is_broad(node.type)
        if broad and not reason:
            findings.append(Finding(
                rel, node.lineno, "H1",
                "宽异常未写理由：需 `# noqa: BLE001 — <为什么必须宽>` 或收窄类型",
            ))
    return findings


def _is_broad(node: ast.expr) -> bool:
    """是否 `Exception` / `BaseException`（含 `except (A, Exception)` 形态）。"""
    if isinstance(node, ast.Name):
        return node.id in ("Exception", "BaseException")
    if isinstance(node, ast.Tuple):
        return any(_is_broad(elt) for elt in node.elts)
    return False


def _apply_allow(findings: list[Finding]) -> tuple[list[Finding], list[str]]:
    hit: set[str] = set()
    kept: list[Finding] = []
    for f in findings:
        key = f"{f.path}:{f.code}"
        if key in ALLOW:
            hit.add(key)
            continue
        kept.append(f)
    stale = sorted(key for key in ALLOW if key not in hit)
    return kept, stale


def scan_paths(roots: list[Path]) -> Report:
    """扫描给定路径，返回报告（不打印、不 exit）。"""
    del SKIPPED_INPUTS[:]
    findings: list[Finding] = []
    files = _iter_py_files(roots)
    report = Report(scanned_files=len(files))
    for path in files:
        rel = path.relative_to(ROOT).as_posix() if ROOT in path.parents else str(path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError) as exc:
            _record_skipped(rel, f"解析失败：{type(exc).__name__}")
            continue
        findings.extend(_scan_tree(tree, rel, source))
    report.findings, report.stale_allows = _apply_allow(findings)
    report.skipped_inputs = list(SKIPPED_INPUTS)
    return report
def _print_report(report: Report, strict: bool) -> int:
    """打印结果并给出退出码。"""
    print("=" * 78)
    print("异常卫生门禁（宽异常必须写理由 / 禁裸 except）")
    print("=" * 78)
    print(f"\n扫描 .py 文件：{report.scanned_files} 个")
    for f in report.findings:
        print(f"  {f.path}:{f.line} {f.code} {f.message}")
    for key in report.stale_allows:
        print(f"  {key} E-ALLOW-STALE 允许清单条目已无命中（腐化，请删除或更新理由）")
    if report.skipped_inputs:
        print(f"\n[告警] {len(report.skipped_inputs)} 处输入未纳入扫描：")
        for rel, reason in report.skipped_inputs:
            print(f"  {rel}: {reason}")
    if report.findings or report.stale_allows:
        print(f"\n[FAIL] {len(report.findings)} 处异常卫生问题")
        return 1
    if report.scanned_files < MIN_PY_FILES:
        print(f"[FAIL] 扫描面不足：仅 {report.scanned_files} 个 .py（下限 {MIN_PY_FILES}）"
              "——拒绝把空/残缺集合当绿")
        return 2
    if strict and report.skipped_inputs:
        print("[FAIL] --strict：存在未纳入扫描的输入")
        return 2
    print("\n[PASS] 宽异常均带理由，无裸 except")
    return 0


def _write_json(path: Path, report: Report, exit_code: int) -> None:
    payload = {
        "scanned_files": report.scanned_files,
        "exit": exit_code,
        "findings": [
            {"path": f.path, "line": f.line, "code": f.code, "message": f.message}
            for f in report.findings
        ],
        "stale_allows": report.stale_allows,
        "skipped_inputs": [{"path": p, "reason": r} for p, r in report.skipped_inputs],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_selftest() -> int:
    """合成样本，逐码自证会响；同时证明合法写法不误报。"""
    import tempfile

    samples = {
        "ok_narrow.py": "try:\n    pass\nexcept ValueError:\n    pass\n",
        "ok_reason.py": "try:\n    pass\nexcept Exception:  # noqa: BLE001 - fallback is fine\n    pass\n",
        "bad_broad.py": "try:\n    pass\nexcept Exception:\n    pass\n",
        "bad_empty.py": "try:\n    pass\nexcept Exception:  # noqa: BLE001 -\n    pass\n",
        "bad_bare.py": "try:\n    pass\nexcept:\n    pass\n",
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, body in samples.items():
            (root / name).write_text(body, encoding="utf-8")
        report = scan_paths([root])
    got = sorted((Path(f.path).name, f.code) for f in report.findings)
    expect = [("bad_bare.py", "H2"), ("bad_broad.py", "H1"), ("bad_empty.py", "H1")]
    if got != expect:
        print(f"[selftest] FAIL 期望 {expect}，实得 {got}", file=sys.stderr)
        return 1
    print("[selftest] ✓ H1/H2 各自触发；收窄类型与带理由的宽异常均不误报")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="check_exception_hygiene", description=__doc__.splitlines()[0])
    ap.add_argument("--json", type=Path, default=None, help="写出 JSON 报告")
    ap.add_argument("--strict", action="store_true", help="未纳入扫描的输入升为 gate")
    ap.add_argument("--selftest", action="store_true", help="合成样本自证")
    ap.add_argument("--paths", default=None, help="逗号分隔的扫描路径（默认仓库根）")
    args = ap.parse_args(argv)
    if args.selftest:
        return _run_selftest()
    roots = [Path(p) for p in args.paths.split(",")] if args.paths else [ROOT]
    report = scan_paths(roots)
    code = _print_report(report, args.strict)
    if args.json:
        _write_json(args.json, report, code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
