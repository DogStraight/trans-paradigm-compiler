"""check_doc_refs.py — 文档调用点引用完整性门禁（docs 管理机器化）。

把"文档增删改时调用点同步"从人工 grep 变成可执行检查（纯 Python 零依赖，
挂 CI）。设计来源：文档治理决策（原 ADR-0011，2026-09-02；判据见
`policy/doc-alignment.md`）。

  规则 D1 [gate]  代码 Doc: 头 → 目标 docs 文件存在
                （补 check_hardcode R3 的缺口：R3 只查 Doc: 头格式存在，
                不查目标文件存在——删文档门禁照样绿，本次精简实证）
  规则 D2 [gate]  导航索引（README / docs-README / MODEL_INDEX）→ 条目存在
  规则 D3 [info]  docs 内 Impl:/Test: 引用 → 文件级存在（::符号 部分不查）
  规则 D4 [info]  docs 文件未被代码 Doc: 或导航索引引用（孤儿提醒）

引用形态（实测盘点）：
- 代码 Doc: 头 114 处为 `Doc: docs/...` 完整路径（docs/ 前缀可含
  decisions/ 子路径）；3 处裸名（tests/fuzz/README.md、
  AGENTS.md）指向非 docs 目标 → D1 只认 `docs/` 前缀。
- 导航索引形态不一：README 用 `./docs/xxx.md` markdown 链接；
  docs/README 与 MODEL_INDEX 多写裸文件名（`case_catalog.md`）或
  `decisions/0001-...md` 子路径——D2 把裸名按 docs 目录内文件名解析，
  解析不到且仓库根存在 → 视为非 docs 引用（AGENTS.md 等）不报。
- Impl:/Test: 行内 `path.py::symbol` / 多文件 `/` 分隔 / glob（`**/*.toml`）
  形态 → D3 只验文件级（glob 非空即过），符号与注释括号不解析。

边界纪律（语义判断不进工具——与"语言知识不进代码"同构）：
- 不做符号级存在性（须 import 代码，脆且重）→ D3 info。
- 不改 CHANGELOG 历史条目（历史不篡改）。
- 不改正文叙述引用（`references.md「章节」` 含锚点语义）。

用法：
  python policy/check_doc_refs.py             # 门禁规则 D1/D2
  python policy/check_doc_refs.py --root <dir>   # 指定扫描根（测试用）

退出码：0 = 门禁规则全干净；1 = 存在门禁违规（D1/D2）。

Doc: policy/doc-alignment.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

# ── 扫描范围 ────────────────────────────────────────────────────────────────
# 导航索引文件（D2 的验证源；相对仓库根）。
# docs/gaps/README.md 是缺口档案登记表：gap 档在表中登记即被索引引用
# （D4 不报孤儿）——2026-09-04 缺口聚合档批量建档后确立。
NAV_FILES: tuple[str, ...] = (
    "README.md",
    "docs/README.md",
    "docs/MODEL_INDEX.md",
    "docs/gaps/README.md",
)

# 代码 Doc: 头目标形态（D1 只认 docs/ 前缀的引用）。两种真实形态：
# 纯行 `Doc: docs/xxx.md` 与带尾注 `Doc: docs/xxx.md（说明）`（仓库主流
# 99/114 处）——只提取路径部分，不要求行尾，允许中文注释/说明跟随。
_DOC_HEADER_RE = re.compile(r"^Doc:\s*(docs/[A-Za-z0-9_./-]+\.md)", re.MULTILINE)

# 文档内 Impl:/Test: 引用行
_IMPL_TEST_RE = re.compile(r"^>\s*(?:Impl|Test):\s*(.+)$", re.MULTILINE)

# 行内候选文件路径（py/toml/glob）；全角括号/注释/::符号 自然截断
_PATH_CANDIDATE_RE = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|toml)")

# 导航索引里的完整路径链接形态（README: ./docs/xxx.md 或 docs/xxx.md）
_DOC_LINK_RE = re.compile(r"\.?/?(?:docs/[A-Za-z0-9_./-]+\.md)")

# 导航索引里反引号包裹的裸文件名 / docs 子路径（decisions/gaps
# 是 docs 下的并列子目录，均可用子路径引用登记）
_BARE_REF_RE = re.compile(
    r"`((?:decisions|gaps)/[A-Za-z0-9_./-]+\.md|[\w-]+\.md)`"
)

# ── 引擎目录（D1 扫描范围：引擎 + 测试 + 工具 + 插件代码都可能有 Doc: 头）──
_SCAN_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "coverage_html",
    "_drafts",  # 讨论草稿暂存区（untracked，不参与门禁）
)


@dataclass(frozen=True)
class Finding:
    """一条检查发现。"""

    rule: str
    path: str
    line: int
    message: str
    detail: str = ""


@dataclass
class RuleResult:
    """单条规则的检查结果。"""

    violations: list[Finding]
    skipped: list[Finding]


@dataclass
class CheckReport:
    """全量检查报告。"""

    results: dict[str, RuleResult]
    doc_files: list[Path]  # docs/ 下全部 .md（相对 root）


# ── 文件收集 ────────────────────────────────────────────────────────────────

def iter_py_files(root: Path) -> Iterator[Path]:
    """产出仓库内全部 .py 文件（相对 root），排除构建/虚拟环境目录。"""
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part in _SCAN_EXCLUDE_DIRS for part in rel.parts):
            continue
        yield rel


def iter_doc_files(root: Path) -> Iterator[Path]:
    """产出 docs/ 下全部 .md 文件（相对 root）。"""
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        for path in sorted(docs_dir.rglob("*.md")):
            yield path.relative_to(root)


# ── D1：代码 Doc: 头目标存在性 ─────────────────────────────────────────────

def rule_d1_doc_headers(root: Path) -> list[Finding]:
    """规则 D1（gate）：代码 Doc: 头引用的 docs 文件必须存在。"""
    findings: list[Finding] = []
    for rel in iter_py_files(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for m in _DOC_HEADER_RE.finditer(text):
            target = m.group(1)
            if not (root / target).is_file():
                line = text[: m.start()].count("\n") + 1
                findings.append(
                    Finding(
                        "D1",
                        str(rel),
                        line,
                        f"Doc: 头引用不存在的文档 '{target}'",
                        "文档删除/改名后未同步（改 references.md 登记或恢复目标）",
                    )
                )
    return findings


# ── D2：导航索引条目存在性 ─────────────────────────────────────────────────

def _resolve_nav_target(candidate: str, root: Path) -> str | None:
    """把导航索引里的候选引用解析为 docs 相对路径；非 docs 引用返回 None。

    形态 1: `docs/xxx.md` / `./docs/xxx.md` → docs/ 下路径
    形态 2: `decisions/xxx.md` / `gaps/xxx.md` → docs/ 下路径
    形态 3: 裸文件名 `xxx.md` → docs/ 目录内按文件名查（唯一命中）
    非 docs（AGENTS.md / tests/... / grammar/...）→ None（跳过）
    """
    cand = candidate.lstrip("./")
    if cand.startswith("docs/"):
        return cand
    if cand.startswith(("decisions/", "gaps/")):
        return f"docs/{cand}"
    if "/" in cand:
        return None  # 其它目录引用（tests/ grammar/ 等），非 docs 目标
    # 裸文件名：docs/ 下按文件名找（可能有 decisions/ 等子目录同名，
    # 取 docs 根优先，其次任意唯一命中；多命中取第一个并视为存在）
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        matches = [p for p in docs_dir.rglob(cand) if p.is_file()]
        if matches:
            return matches[0].relative_to(root).as_posix()
        # docs/ 下没有：仓库根存在（AGENTS.md 等）→ 非 docs 引用
        if (root / cand).is_file():
            return None
        return f"docs/{cand}"  # docs 下与根都没有 → 视为 docs 引用缺失
    return None


def _d2_finding(nav_rel: str, line_no: int, line: str, target: str) -> Finding:
    """D2 诊断（索引引用不存在的文档）。"""
    return Finding(
        "D2", nav_rel, line_no, f"索引引用不存在的文档 '{target}'", line.strip()[:120]
    )


def _check_nav_line(
    line: str, nav_rel: str, line_no: int, root: Path, findings: list[Finding]
) -> None:
    """一行内的两类引用形态：完整路径链接 + 反引号裸文件名/子路径。"""
    for m in _DOC_LINK_RE.finditer(line):
        target = _resolve_nav_target(m.group(0), root)
        if target and not (root / target).is_file():
            findings.append(_d2_finding(nav_rel, line_no, line, target))
    # 反引号裸文件名 / docs 子路径形态（避免重复计数：跳过已被完整路径正则
    # 覆盖的片段）
    for m in _BARE_REF_RE.finditer(line):
        cand = m.group(1)
        if "docs/" in line[max(0, m.start() - 8): m.end()]:
            continue
        target = _resolve_nav_target(cand, root)
        if target and not (root / target).is_file():
            findings.append(_d2_finding(nav_rel, line_no, line, target))


def rule_d2_nav_indexes(root: Path) -> list[Finding]:
    """规则 D2（gate）：导航索引引用的 docs 文件必须存在。"""
    findings: list[Finding] = []
    for nav_rel in NAV_FILES:
        nav_path = root / nav_rel
        if not nav_path.is_file():
            continue
        text = nav_path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in _iter_md_lines(text):
            _check_nav_line(line, nav_rel, line_no, root, findings)
    return findings


# ── D3：Impl:/Test: 文件级存在性（info） ────────────────────────────────────

def _iter_md_lines(text: str) -> Iterator[tuple[int, str]]:
    """逐行产出 md 文本，跳过 ``` 代码块内的行（示例/示意不是真实引用）。"""
    in_block = False
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            yield line_no, line


def _d3_finding(doc_rel, line_no: int, message: str) -> Finding:
    """D3 诊断（info 级：Impl/Test 引用缺失）。"""
    return Finding("D3", str(doc_rel), line_no, message)


def _check_d3_candidate(
    root: Path, doc_rel, line_no: int, kind: str, cand: str, dir_candidates: list[str]
) -> Finding | None:
    """单个候选 → 缺失则出诊断（返回 None = 通过/不归 D3 管）。

    - `docs/` 前缀：指向 docs 自身的引用交给 D2 → 跳过
    - 裸文件名（无目录前缀）：继承本行最后一个带目录候选的目录
      （`a/b.py / c.py` → c.py 解析为 a/c.py）
    - 含 `*` 的 glob 形态：非空即过
    """
    if cand.startswith("docs/"):
        return None
    if "/" not in cand:
        base_dir = Path(dir_candidates[-1]).parent if dir_candidates else None
        resolved = (Path(base_dir) / cand) if base_dir else Path(cand)
        if (root / resolved).is_file():
            return None
        return _d3_finding(doc_rel, line_no, f"{kind}: 引用的文件不存在 '{cand}'")
    if "*" in cand:
        if list(root.glob(cand)):
            return None
        return _d3_finding(doc_rel, line_no, f"{kind}: glob 无匹配 '{cand}'")
    if (root / cand).is_file():
        return None
    return _d3_finding(doc_rel, line_no, f"{kind}: 引用的文件不存在 '{cand}'")


def _check_d3_line(
    root: Path, doc_rel, line_no: int, line: str, findings: list[Finding]
) -> None:
    """一行 `Impl:` / `Test:` 逐候选检查。"""
    m = _IMPL_TEST_RE.match(line.strip())
    if not m:
        return
    kind = "Impl" if "Impl" in m.group(0) else "Test"
    body = m.group(1)
    # 本行已解析出的候选（带目录的），供裸文件名继承目录
    dir_candidates = [c for c in _PATH_CANDIDATE_RE.findall(body) if "/" in c]
    for cand in _PATH_CANDIDATE_RE.findall(body):
        finding = _check_d3_candidate(
            root, doc_rel, line_no, kind, cand, dir_candidates
        )
        if finding is not None:
            findings.append(finding)


def rule_d3_impl_test_files(root: Path) -> list[Finding]:
    """规则 D3（info）：docs 内 Impl:/Test: 引用的文件级存在（glob 非空即过）。

    支持同一行 `/` 分隔的多候选；裸文件名（无目录前缀）继承本行前一个有
    目录候选的目录（`a/b.py / c.py` → c.py 解析为 a/c.py）。
    """
    findings: list[Finding] = []
    for doc_rel in iter_doc_files(root):
        text = (root / doc_rel).read_text(encoding="utf-8", errors="replace")
        for line_no, line in _iter_md_lines(text):
            _check_d3_line(root, doc_rel, line_no, line, findings)
    return findings


# ── D4：孤儿文档提醒（info） ────────────────────────────────────────────────

def rule_d4_orphan_docs(root: Path, d1_targets: set[str], d2_targets: set[str]) -> list[Finding]:
    """规则 D4（info）：docs 文件未被代码 Doc: 或导航索引引用（孤儿提醒）。"""
    referenced = d1_targets | d2_targets
    findings: list[Finding] = []
    for doc_rel in iter_doc_files(root):
        doc = doc_rel.as_posix()
        # 导航文件自身（docs 导航 / 跳转表）不算孤儿；decisions/README 由
        # docs-README 决策行引用（不豁免，靠真实引用）
        if doc in ("docs/README.md", "docs/MODEL_INDEX.md"):
            continue
        if doc not in referenced:
            findings.append(
                Finding(
                    "D4",
                    doc,
                    1,
                    "docs 文件未被代码 Doc: 或导航索引引用（孤儿）",
                    "新增文档请登记 MODEL_INDEX/docs-README，或删除",
                )
            )
    return findings


# ── 汇总与 CLI ──────────────────────────────────────────────────────────────

def collect_findings(root: Path) -> CheckReport:
    """跑全部规则，返回 CheckReport（测试与 CLI 共用入口）。"""
    d1 = rule_d1_doc_headers(root)
    d2 = rule_d2_nav_indexes(root)
    # 供 D4 使用：已引用的 docs 目标集合
    d1_targets = _collect_d1_targets(root)
    d2_targets = _collect_d2_targets(root)
    d4 = rule_d4_orphan_docs(root, d1_targets, d2_targets)
    return CheckReport(
        results={
            "D1": RuleResult(d1, []),
            "D2": RuleResult(d2, []),
            "D3": RuleResult(rule_d3_impl_test_files(root), []),
            "D4": RuleResult(d4, []),
        },
        doc_files=list(iter_doc_files(root)),
    )


def _collect_d1_targets(root: Path) -> set[str]:
    """D1 扫描中出现的全部 docs 目标（供 D4 判孤儿）。"""
    targets: set[str] = set()
    for rel in iter_py_files(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for m in _DOC_HEADER_RE.finditer(text):
            targets.add(m.group(1))
    return targets


def _nav_line_targets(line: str, root: Path) -> Iterator[str]:
    """一行内的引用形态 → 解析出的 docs 目标（非 docs 引用不产出）。"""
    for m in _DOC_LINK_RE.finditer(line):
        t = _resolve_nav_target(m.group(0), root)
        if t:
            yield t
    for m in _BARE_REF_RE.finditer(line):
        cand = m.group(1)
        if "docs/" in line[max(0, m.start() - 8): m.end()]:
            continue  # 同一引用已按完整路径形态处理
        t = _resolve_nav_target(cand, root)
        if t:
            yield t


def _collect_d2_targets(root: Path) -> set[str]:
    """D2 扫描中出现的全部 docs 目标（供 D4 判孤儿）。

    口径与 D2 规则不同：这里按**整份文本**逐行收集（含 ``` 代码块内的示例
    引用），D2 规则则跳过代码块——沿用原实现的这种不对称（孤儿集是超集）。
    """
    targets: set[str] = set()
    for nav_rel in NAV_FILES:
        nav_path = root / nav_rel
        if not nav_path.is_file():
            continue
        text = nav_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            targets.update(_nav_line_targets(line, root))
    return targets


def _print_findings(title: str, findings: Sequence[Finding]) -> None:
    if not findings:
        print(f"  {title}: 0")
        return
    print(f"  {title}: {len(findings)}")
    for f in findings:
        loc = f"{f.path}:{f.line}"
        suffix = f" — {f.detail}" if f.detail else ""
        print(f"      {loc}: {f.message}{suffix}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_doc_refs",
        description="文档调用点引用完整性门禁（docs 增删改自动防断链）",
    )
    parser.add_argument("--root", default=None, help="扫描根目录（默认仓库根；测试/诊断用）")
    parser.add_argument("--quiet", action="store_true", help="只输出违规与结论")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    report = collect_findings(root)
    results = report.results

    gate: set[str] = {"D1", "D2"}

    if not args.quiet:
        print(f"[文档门禁] docs 文件 {len(report.doc_files)} 个（扫描范围含全部 .py）")
    for rule_id in ("D1", "D2", "D3", "D4"):
        res = results[rule_id]
        label = "gate" if rule_id in gate else "info"
        if not args.quiet:
            print(f"── 规则 {rule_id} [{label}]")
        _print_findings(f"{rule_id} 发现", res.violations)

    gate_findings = sum(len(results[r].violations) for r in gate)
    if gate_findings:
        print(f"[FAIL] 门禁违规 {gate_findings} 处（{', '.join(sorted(gate))}）")
        return 1
    print("[PASS] 文档调用点门禁全干净")
    return 0


if __name__ == "__main__":
    sys.exit(main())
