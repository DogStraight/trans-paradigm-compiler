#!/usr/bin/env python3
"""tools/scan_redundant.py — 冗余残留扫描 +（可选）清理脚手架

审查会话的复用工具：扫描仓库里"建议删除"的残留物，默认**只报告不删除**。
删除必须先过"删除判据"（policy/doc-alignment.md，判据 A/B/C），脚本只做
**机械识别**，判据归属仍需人/agent 复核——脚本不替你判定"该不该删"。

扫描三类（顺序与 implement-task 审查清单一致）：
  1. scratch    —— 草稿/临时产物：`_drafts/`、`*.bak|*.orig|*.rej|*~|*.tmp|*.swp`、
                   `probe_*`/`_probe*`/`scratch_*`/`dbg_*` 命名脚本、根目录调试日志
  2. ignored    —— 被 .gitignore 忽略的大体积构建产物（dist/ 等），可选 --clean
  3. dangling   —— 指向 scratch 区的**已悬空引用**：tracked 文件里引用了
                   scratch 路径但目标不存在（删除判据 B3「引已删目标」）

只读 git 与文件系统，零第三方依赖。默认 dry-run。

用法：
    python tools/scan_redundant.py                  # 全量报告（dry-run）
    python tools/scan_redundant.py --only scratch   # 只看草稿残留
    python tools/scan_redundant.py --live-refs      # 额外列出"仍被引用的草稿"（删除前须迁走）
    python tools/scan_redundant.py --json out.json  # 机器可读清单

    # 真正删除（危险，需显式 --yes）：
    python tools/scan_redundant.py --clean scratch --yes
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 草稿/临时目录（与 .gitignore 的 scratch 区一致）
SCRATCH_DIRS = ("_drafts",)
TEMP_SUFFIXES = (".bak", ".orig", ".rej", "~", ".tmp", ".swp")
# 调试/探针脚本命名（根目录或任意目录下的散落产物）
PROBE_NAME_RE = re.compile(r"^(probe_|_probe|scratch_|dbg_|debug_|tmp_)")
# 根目录调试日志
ROOT_LOG_RE = re.compile(r"^(_?parser_debug\.log|pytest_.*\.txt|.*\.log)$")
# 构建/缓存产物目录（gitignored）
BUILD_DIRS = ("dist", "build", ".pytest_cache", "trans_paradigm_compiler.egg-info",
              "__pycache__", "coverage_html")

# 引用扫描时跳过的目录（本身是 scratch/产物，不算"引用者"）
REF_SKIP = set(SCRATCH_DIRS) | set(BUILD_DIRS) | {".git", "node_modules", ".venv"}

# 引用扫描时读取失败的输入（不能静默丢；JSON 与告警共享此清单）
SKIPPED_INPUTS: list[tuple[str, str]] = []


def _record_skipped_input(rel: str, reason: str) -> None:
    entry = (rel, reason)
    if entry not in SKIPPED_INPUTS:
        SKIPPED_INPUTS.append(entry)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    )
    return [l for l in out.stdout.splitlines() if l.strip()]


def _ignored_entries() -> list[str]:
    """gitignored 的顶层条目（含未跟踪的 scratch 区）。"""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--ignored", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    entries = []
    for line in out.stdout.splitlines():
        if line.startswith("!! "):
            entries.append(line[3:].strip().strip("/"))
    return entries


def _classify_loose(p: Path, rel: str, tracked: set[str]) -> dict | None:
    """单个散落文件的分类（None = 不是残留物）。

    tracked 文件不凭文件名判定（须走删除判据 A 逐条复核，如
    core/debug_report.py 是正式工具），故探针/日志两类只标未跟踪的。
    """
    name = p.name
    size = p.stat().st_size
    if name.endswith(TEMP_SUFFIXES):
        return {"kind": "temp-suffix", "path": rel, "files": 1, "bytes": size}
    if PROBE_NAME_RE.match(name) and p.suffix in (".py", ".ps1", ".sh"):
        if rel not in tracked:
            return {"kind": "probe-script", "path": rel, "files": 1,
                    "bytes": size, "tracked": False}
        return None
    if "/" not in rel and ROOT_LOG_RE.match(name) and rel not in tracked:
        return {"kind": "root-log", "path": rel, "files": 1, "bytes": size}
    return None


def _scan_scratch_dir(d: str) -> dict:
    """草稿目录一项（文件数 + 总字节）。"""
    files = [p for p in (ROOT / d).rglob("*") if p.is_file()]
    return {"kind": "scratch-dir", "path": d, "files": len(files),
            "bytes": sum(p.stat().st_size for p in files)}


def scan_scratch() -> list[dict]:
    """草稿/临时文件清单（含大小），按体积降序。"""
    found = [_scan_scratch_dir(d) for d in SCRATCH_DIRS if (ROOT / d).is_dir()]
    tracked = set(_tracked_files())
    for p in ROOT.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts or ".git" in p.parts:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in SCRATCH_DIRS):
            continue
        hit = _classify_loose(p, rel, tracked)
        if hit is not None:
            found.append(hit)
    found.sort(key=lambda x: -x["bytes"])
    return found


def scan_ignored() -> list[dict]:
    """gitignored 的大体积产物目录。"""
    out = []
    for e in _ignored_entries():
        p = ROOT / e
        if not p.is_dir() or e in SCRATCH_DIRS:
            continue
        files = [q for q in p.rglob("*") if q.is_file()]
        out.append({"kind": "ignored-dir", "path": e, "files": len(files),
                    "bytes": sum(q.stat().st_size for q in files)})
    out.sort(key=lambda x: -x["bytes"])
    return out


def _reference_hits(needle_prefix: str) -> list[dict]:
    """tracked 文件中对 scratch 路径的引用（悬空与否由调用方判定）。"""
    hits = []
    for rel in _tracked_files():
        if any(rel == d or rel.startswith(d + "/") for d in REF_SKIP):
            continue
        p = ROOT / rel
        if p.suffix not in (".py", ".md", ".toml", ".json", ".ps1", ".sh", ".yml",
                            ".yaml", ".txt", ".cfg", ".ini"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            _record_skipped_input(rel, f"读取失败: {exc}")
            continue
        if needle_prefix not in text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in re.finditer(re.escape(needle_prefix) + r"[A-Za-z0-9_./\-]*", line):
                target = m.group(0).rstrip(".,;)'\"")
                hits.append({"file": rel, "line": i, "target": target})
    return hits


def _is_convention_mention(target: str) -> bool:
    """是否只是"草稿区在哪"的**约定陈述**（`_drafts/` 裸目录名），不是具体文件指针。

    判定依据：政策/README 里"讨论草稿放 `_drafts/`"这类句子在草稿清空后**照旧成立**
    （草稿区本就是"用完即删"），不是悬空引用（判据 B3 指的是指向**具体文件**的失锚）。
    """
    return target.rstrip("/") in SCRATCH_DIRS


def scan_refs() -> dict:
    """引用体检：仍存在的草稿被谁引用（live）+ 已悬空引用（dangling）。

    裸目录名（`_drafts/`）的提及算**约定陈述**，单独归入 `conventions`，不计悬空——
    否则政策文档会被长期误报，真正该修的失锚反而被噪音淹没。
    """
    SKIPPED_INPUTS.clear()
    live, dangling, conventions = [], [], []
    for d in SCRATCH_DIRS:
        for h in _reference_hits(d + "/"):
            exists = (ROOT / h["target"]).exists()
            h["exists"] = exists
            if exists:
                live.append(h)
            elif _is_convention_mention(h["target"]):
                conventions.append(h)
            else:
                dangling.append(h)
    return {"live": live, "dangling": dangling, "conventions": conventions}


def _fmt(n: int) -> str:
    return f"{n/1024/1024:.1f} MB" if n >= 1024 * 1024 else f"{n/1024:.0f} KB"


def _report_refs(refs: dict, live: bool) -> None:
    """引用体检段：悬空引用（B3）+ 可选"仍被引用"清单。"""
    dang = refs["dangling"]
    conv = refs.get("conventions") or []
    print(f"\n[dangling] 已悬空引用（删除判据 B3）：{len(dang)} 条"
          f"（另 {len(conv)} 条为「草稿区在哪」的约定陈述，不计）")
    for h in dang:
        print(f"  - {h['file']}:{h['line']} -> {h['target']} (不存在)")
    if not live:
        return
    lv = refs["live"]
    print(f"\n[live-refs] 仍存在但被引用的草稿：{len(lv)} 条（删除前须迁走/改锚）")
    seen: set[str] = set()
    for h in lv:
        if h["target"] in seen:
            continue
        seen.add(h["target"])
        print(f"  ! {h['target']}  <- {h['file']}:{h['line']}")


def _report_group(kind: str, items: list[dict], limit: int = 25) -> None:
    """单类残留段：前 limit 项明细 + 溢出计数。"""
    tot = sum(i["bytes"] for i in items)
    print(f"\n[{kind}] {len(items)} 项 / {_fmt(tot)}")
    for i in items[:limit]:
        extra = f" ({i['files']} files)" if i["files"] > 1 else ""
        trk = ""
        if i.get("tracked") is not None:
            trk = " [tracked]" if i["tracked"] else " [untracked]"
        print(f"  - {i['path']}{extra}{trk}  {_fmt(i['bytes'])}")
    if len(items) > limit:
        print(f"  ... 另 {len(items) - limit} 项")


def _skipped_payload() -> list[dict]:
    return [{"path": path, "reason": reason} for path, reason in SKIPPED_INPUTS]


def _report_skipped_inputs() -> None:
    if not SKIPPED_INPUTS:
        return
    print(f"\n[告警] {len(SKIPPED_INPUTS)} 处输入未能读取，未纳入统计：")
    for path, reason in SKIPPED_INPUTS:
        print(f"  {path}: {reason}")


def report(findings: list[dict], refs: dict | None, live: bool) -> None:
    print("=" * 78)
    print("冗余残留扫描（dry-run，未删除任何文件）")
    print("=" * 78)
    if refs is not None:
        _report_refs(refs, live)
    groups: dict[str, list[dict]] = {}
    for f in findings:
        groups.setdefault(f["kind"], []).append(f)
    for kind in ("scratch-dir", "ignored-dir", "temp-suffix", "probe-script", "root-log"):
        if groups.get(kind):
            _report_group(kind, groups[kind])
    print("\n提示：删除前按 policy/doc-alignment.md「删除判据」逐条复核；"
          "清理需显式 --clean <kind> --yes。")
    _report_skipped_inputs()


def _clean(findings: list[dict], kinds: set[str]) -> None:
    targets = [f for f in findings if f["kind"] in kinds]
    for t in targets:
        p = ROOT / t["path"]
        if not p.exists():
            continue
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        else:
            p.unlink()
        print(f"  removed: {t['path']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="冗余残留扫描（默认 dry-run）")
    ap.add_argument("--only", choices=["scratch", "ignored"], help="只看某类")
    ap.add_argument("--live-refs", action="store_true", help="列出仍被引用的草稿")
    ap.add_argument("--json", metavar="PATH", help="写出 JSON 清单")
    ap.add_argument("--clean", nargs="+", metavar="KIND",
                    help="删除指定 kind（scratch-dir/ignored-dir/...）；需搭配 --yes")
    ap.add_argument("--yes", action="store_true", help="确认删除（不加则只打印计划）")
    args = ap.parse_args(argv)

    findings: list[dict] = []
    if args.only != "ignored":
        findings += scan_scratch()
    if args.only != "scratch":
        findings += scan_ignored()

    refs = scan_refs()

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"findings": findings, "refs": refs, "skipped_inputs": _skipped_payload()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[json] {args.json}")

    report(findings, refs, args.live_refs)

    if args.clean:
        kinds = set(args.clean)
        print(f"\n[clean] 计划删除 kind={sorted(kinds)}")
        if not args.yes:
            print("  未加 --yes：仅打印计划，未删除。")
            return 0
        _clean(findings, kinds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
