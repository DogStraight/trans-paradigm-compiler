"""doc_sync.py — 文档调用点同步层（rename/delete 辅助写操作）。

门禁层（check_doc_refs.py）解决"断链被发现"；本工具解决"改名/删除时
调用点一起改"——复用 check_doc_refs 的引用解析（同一组正则 +
_resolve_nav_target），保证"门禁认的引用 = 同步层改的引用"，两边不漂移。

子命令（全部默认 --dry-run 只报告，--apply 才落盘）：
  python policy/doc_sync.py refs <target>
      列出某 docs 文件被谁引用（代码 Doc: / 导航索引 / 文档正文 / TOML）
  python policy/doc_sync.py rename <old> <new> [--apply]
      改 docs 文件路径 → 同步改全部引用点；最后 git rm/mv 提示由用户执行
  python policy/doc_sync.py delete <target> [--apply]
      删除 docs 文件：--apply 时清理机械可清的引用（Doc: 头行 / 独占
      表格行）+ 删文件；含正文叙述/行内并列引用则拒绝并列出人工清单

机械可改形态（与门禁 D1/D2 解析范围一致）：
- 代码文件头 `Doc: docs/...`（行内整路径）
- 导航索引/正文里的 `docs/...`、`./docs/...`、子目录前缀
  `decisions/...`、裸文件名 `xxx.md`
明确不做（同门禁边界）：`Impl:`/`Test:` 的 `::符号`、正文叙述锚点
（`references.md「章节」`）、CHANGELOG 历史条目。

闭环：rename/delete 后用 check_doc_refs.py 验证 D1/D2 仍绿——同步层
不绕过门禁，只把"人工 grep 同步"变成"半自动 + 门禁兜底"。

Doc: policy/doc-alignment.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import check_doc_refs as gate  # 同目录复用门禁解析（同一组正则）

# Windows 控制台/管道默认编码（GBK/cp1252）编不了中文——非 ASCII 输出会让
# 同步工具自己崩。本进程自护 stdout/stderr（reconfigure 只影响本进程，
# 比替换 sys.stdout 安全；受限环境拒绝则忽略）。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — 受限环境无 reconfigure，忽略
        pass

# ── 扫描范围 ────────────────────────────────────────────────────────────────
# 引用点可能出现在：全部 .py（Doc: 头）/ .md（导航+正文+skills）/
# .toml（grammar 插件注释）。跳过构建目录与 CHANGELOG（历史不篡改）。
_SYNC_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "coverage_html",
    "packaging",
    "_drafts",  # 讨论草稿暂存区（untracked，不参与门禁/同步）
)
_SYNC_EXCLUDE_FILES: tuple[str, ...] = ("CHANGELOG.md",)


@dataclass(frozen=True)
class _Ref:
    """一条引用点（字符区间定位，供精确替换）。"""

    path: str  # 相对 root
    line: int  # 1-based
    start: int  # 全文字符区间（含）
    end: int  # 全文字符区间（不含）
    text: str  # 原始引用文本（不含反引号）
    target: str  # 解析出的 docs 路径（docs/...）
    in_table: bool = False  # 是否整行独占（表格行/列表行）


# ── 引用点收集（与门禁同一解析）────────────────────────────────────────────

def _iter_scan_files(root: Path) -> Iterator[Path]:
    """产出全部可能含 docs 引用的文件（相对 root）。"""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _SYNC_EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.name in _SYNC_EXCLUDE_FILES:
            continue
        if rel.suffix not in (".py", ".md", ".toml"):
            continue
        yield rel


def _line_of(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def _md_codeblock_ranges(text: str) -> list[tuple[int, int]]:
    """md 代码块 ``` 的字符区间列表（示例内的引用不算真实引用点）。"""
    ranges: list[tuple[int, int]] = []
    start = -1
    for m in re.finditer(r"^```", text, re.MULTILINE):
        if start < 0:
            start = m.start()
        else:
            ranges.append((start, m.end()))
            start = -1
    return ranges


class _RefCollector:
    """单文件的引用点收集器：区间重叠去重（保留先收集的最长/最早区间）。"""

    def __init__(self, rel: Path, text: str):
        self.rel = rel
        self.text = text
        self.collected: list[tuple[int, int, _Ref]] = []

    def _overlaps(self, start: int, end: int) -> bool:
        return any(s < end and start < e for s, e, _ in self.collected)

    def add(self, start: int, end: int, text_val: str, tgt: str | None) -> None:
        """登记一个引用点（与已收区间重叠 → 丢弃）。"""
        if self._overlaps(start, end):
            return
        self.collected.append(
            (
                start,
                end,
                _Ref(
                    self.rel.as_posix(),
                    _line_of(self.text, start),
                    start,
                    end,
                    text_val,
                    tgt or "",
                ),
            )
        )

    def refs(self) -> list[_Ref]:
        """本文件收集到的引用点（按登记顺序）。"""
        return [r for _, _, r in self.collected]


def _collect_doc_header(collector: "_RefCollector", text: str, target: str) -> None:
    """形态 1：代码 Doc: 头（替换区间 = group(1) 路径部分）。

    .py 对 docs 的引用只有 Doc: 头这一种形态（仓库 114 处实证）——代码字符串/
    注释里的 docs/ 路径是数据或叙述，不是引用，不收集（避免 rename 误伤测试
    夹具）。
    """
    for m in gate._DOC_HEADER_RE.finditer(text):
        tgt = m.group(1)
        if tgt == target:
            collector.add(m.start(1), m.end(1), m.group(0).strip(), tgt)


def _collect_doc_links(
    collector: "_RefCollector", root: Path, text: str, target: str, code_blocks: list
) -> None:
    """形态 2：docs/ 链接形态（README ./docs/...、正文 docs/...）。"""
    for m in gate._DOC_LINK_RE.finditer(text):
        if any(s <= m.start() < e for s, e in code_blocks):
            continue
        tgt = gate._resolve_nav_target(m.group(0), root)
        if tgt == target:
            collector.add(m.start(), m.end(), m.group(0), tgt)


def _collect_bare_refs(
    collector: "_RefCollector", root: Path, text: str, target: str, code_blocks: list
) -> None:
    """形态 3：反引号裸名 / 子目录前缀（替换区间 = group(1) 内部，保留反引号）。"""
    for m in gate._BARE_REF_RE.finditer(text):
        if any(s <= m.start() < e for s, e in code_blocks):
            continue
        cand = m.group(1)
        if "docs/" in text[max(0, m.start() - 8): m.end()]:
            continue  # 同一引用已按完整路径形态处理
        tgt = gate._resolve_nav_target(cand, root)
        if tgt == target:
            collector.add(m.start(1), m.end(1), cand, tgt)


def _refs_in_file(root: Path, rel: Path, target: str) -> Iterator[_Ref]:
    """单文件内的引用点（读失败 → 无产出）。"""
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    code_blocks = _md_codeblock_ranges(text) if rel.suffix == ".md" else []
    collector = _RefCollector(rel, text)
    if rel.suffix == ".py":
        _collect_doc_header(collector, text, target)
    else:
        # 形态 2/3 仅对 .md/.toml（导航索引/文档正文/TOML 注释）
        _collect_doc_links(collector, root, text, target, code_blocks)
        _collect_bare_refs(collector, root, text, target, code_blocks)
    yield from collector.refs()


def collect_refs(root: Path, target: str) -> list[_Ref]:
    """收集引用 target（docs 相对路径）的全部引用点。

    同一组正则与 check_doc_refs 完全一致：_DOC_HEADER_RE（代码 Doc: 头）、
    _DOC_LINK_RE（docs/ 链接形态）、_BARE_REF_RE（反引号裸名/子目录前缀）。
    区间重叠去重见 `_RefCollector`，各形态细则见 `_collect_*`。
    """
    target = target.replace("\\", "/").lstrip("./")
    if not target.startswith("docs/"):
        target = f"docs/{target}"
    refs: list[_Ref] = []
    for rel in _iter_scan_files(root):
        refs.extend(_refs_in_file(root, rel, target))
    return refs


# ── 文本替换 ────────────────────────────────────────────────────────────────

def _other_md_refs(root: Path, line: str, target: str) -> bool:
    """行内除 target 外是否还引用其它 docs 文件（True = 行内并列 → 人工）。

    在该行重跑 _DOC_LINK_RE / _BARE_REF_RE，解析出全部 docs target；存在
    不同于 target 的引用即判定为并列（不能整行删）。
    """
    for m in gate._DOC_LINK_RE.finditer(line):
        tgt = gate._resolve_nav_target(m.group(0), root)
        if tgt and tgt != target:
            return True
    for m in gate._BARE_REF_RE.finditer(line):
        cand = m.group(1)
        tgt = gate._resolve_nav_target(cand, root)
        if tgt and tgt != target:
            return True
    return False


def _replacement_for(ref: _Ref, new_doc: str) -> str | None:
    """计算 ref 的替换文本；非机械可改返回 None（留人工）。

    new_doc 为 docs 相对路径（docs/bar.md）。替换区间是引用中的路径部分
    （collect_refs 按 group(1) 定位），故替换文本一律为纯路径，不带
    `Doc: `/反引号等包裹符——包裹符在区间外自然保留：
    - Doc: 头（区间=路径）→ `docs/bar.md`
    - `./docs/old` → `./docs/bar.md`（保留 ./）
    - 子目录前缀 `decisions/old` → 新文档同前缀或 docs/ 全路径
    - 裸名 `old.md` → 新文档 basename（若仍在 docs 根）或 docs/ 全路径
    """
    new_doc = new_doc.replace("\\", "/").lstrip("./")
    if not new_doc.startswith("docs/"):
        new_doc = f"docs/{new_doc}"
    old_text = ref.text
    new_bare = new_doc[len("docs/"):]  # bar.md 或 decisions/bar.md

    # ./docs/ 前缀保留（区间含 ./，替换文本带 ./）
    if old_text.startswith("./docs/"):
        return f"./{new_doc}"
    # Doc: 头（区间=路径本身）→ 纯路径
    if old_text.startswith("Doc: "):
        return new_doc
    # 裸名（无斜杠）：新文档仍在 docs 根 → basename；否则全路径
    if "/" not in old_text and not old_text.startswith("docs/"):
        return new_bare if "/" not in new_bare else new_doc
    # 子目录前缀（decisions/）或 docs/ 全路径
    if old_text.startswith("decisions/"):
        return new_bare  # 保留子目录前缀风格
    if old_text.startswith("docs/"):
        return new_doc
    return None  # 未知形态 → 人工


def _apply_replacements(root: Path, refs: Sequence[_Ref], new_doc: str) -> list[_Ref]:
    """按引用点做文本替换；返回无法机械处理的引用（人工清单）。

    按文件聚合、从后往前替换（避免区间漂移）；仅 --apply 调用。
    """
    manual: list[_Ref] = []
    by_file: dict[str, list[_Ref]] = {}
    for ref in refs:
        by_file.setdefault(ref.path, []).append(ref)
    for rel, file_refs in by_file.items():
        path = root / rel
        text = path.read_text(encoding="utf-8")
        # 从后往前替换，保持区间有效
        pending = []
        for ref in sorted(file_refs, key=lambda r: r.start, reverse=True):
            repl = _replacement_for(ref, new_doc)
            if repl is None:
                manual.append(ref)
                continue
            pending.append((ref, repl))
        for ref, repl in pending:
            text = text[: ref.start] + repl + text[ref.end :]
        path.write_text(text, encoding="utf-8")
    return manual


# ── 输出 ────────────────────────────────────────────────────────────────────

def _print_refs(refs: Sequence[_Ref]) -> None:
    if not refs:
        print("  无引用点（可直接改名/删除）")
        return
    print(f"  引用点 {len(refs)} 处：")
    for ref in sorted(refs, key=lambda r: (r.path, r.line)):
        print(f"      {ref.path}:{ref.line}  {ref.text}")


# ── 子命令 ──────────────────────────────────────────────────────────────────

def _cmd_refs(root: Path, target: str) -> int:
    print(f"[refs] {target} 的引用点：")
    _print_refs(collect_refs(root, target))
    return 0


def cmd_rename(root: Path, old: str, new: str, apply: bool) -> int:
    old_doc = old.replace("\\", "/").lstrip("./")
    if not old_doc.startswith("docs/"):
        old_doc = f"docs/{old_doc}"
    old_path = root / old_doc
    if not old_path.is_file():
        print(f"[rename] 源文档不存在: {old_doc}")
        return 1
    new_doc = new.replace("\\", "/").lstrip("./")
    if not new_doc.startswith("docs/"):
        new_doc = f"docs/{new_doc}"

    refs = collect_refs(root, old_doc)
    print(f"[rename] {old_doc} → {new_doc}（引用点 {len(refs)} 处）")
    _print_refs(refs)
    if not apply:
        print("[rename] dry-run：加 --apply 落盘；落盘后请 git add -A 并跑 check_doc_refs.py 验证")
        return 0

    manual = _apply_replacements(root, refs, new_doc)
    if manual:
        print(f"[rename] 以下 {len(manual)} 处无法机械替换，请人工处理：")
        _print_refs(manual)
    # 移动文件本身
    os.makedirs(old_path.parent, exist_ok=True)
    new_path = root / new_doc
    os.makedirs(new_path.parent, exist_ok=True)
    os.replace(old_path, new_path)
    print(f"[rename] 已移动 {old_doc} → {new_doc}")
    print("[rename] 请 git add -A && python policy/check_doc_refs.py 验证")
    return 0


def _refs_by_file(refs: Sequence[_Ref]) -> dict[str, list[_Ref]]:
    """引用点按文件归组。"""
    out: dict[str, list[_Ref]] = {}
    for ref in refs:
        out.setdefault(ref.path, []).append(ref)
    return out


def _removable_lines(
    root: Path, rel: str, file_refs: list[_Ref], target_doc: str
) -> tuple[list[int], list[_Ref]]:
    """单文件判定 → (可机械清理的行号（0-based）, 需人工的引用）。

    机械可清：代码 Doc: 头行（整行删）/ 非 .py 的独占行（行内除本引用外无
    其它 .md 引用 → 整行删）；行内并列引用 → 人工。
    """
    lines = (root / rel).read_text(encoding="utf-8").splitlines(keepends=True)
    is_py = rel.endswith(".py")
    removable: list[int] = []
    manual: list[_Ref] = []
    for ref in sorted(file_refs, key=lambda r: r.start, reverse=True):
        line_idx = ref.line - 1
        if line_idx >= len(lines):
            continue
        line = lines[line_idx]
        if is_py and gate._DOC_HEADER_RE.search(line):
            removable.append(line_idx)
        elif not is_py and not _other_md_refs(root, line, target_doc):
            removable.append(line_idx)
        else:
            manual.append(ref)
    return removable, manual


def _judge_removable(
    root: Path, by_file: dict[str, list[_Ref]], target_doc: str
) -> tuple[dict[str, list[int]], list[_Ref]]:
    """阶段 1：只读判定（不落盘）→ (可清理行号表, 人工清单)。"""
    removable: dict[str, list[int]] = {}
    manual: list[_Ref] = []
    for rel, file_refs in by_file.items():
        line_idxs, need_manual = _removable_lines(root, rel, file_refs, target_doc)
        if line_idxs:
            removable[rel] = line_idxs
        manual.extend(need_manual)
    return removable, manual


def _drop_lines(root: Path, removable: dict[str, list[int]]) -> None:
    """阶段 2：按行号倒序删行（防区间漂移）后落盘。"""
    for rel, line_idxs in removable.items():
        path = root / rel
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for line_idx in sorted(set(line_idxs), reverse=True):
            del lines[line_idx]
        path.write_text("".join(lines), encoding="utf-8")


def cmd_delete(root: Path, target: str, apply: bool) -> int:
    """删除文档并清理引用点（原子：任一引用非机械可清则完全不动）。"""
    target_doc = target.replace("\\", "/").lstrip("./")
    if not target_doc.startswith("docs/"):
        target_doc = f"docs/{target_doc}"
    target_path = root / target_doc
    if not target_path.is_file():
        print(f"[delete] 目标不存在: {target_doc}")
        return 1

    refs = collect_refs(root, target_doc)
    print(f"[delete] {target_doc} 的引用点 {len(refs)} 处：")
    _print_refs(refs)
    if not apply:
        print("[delete] dry-run：加 --apply 清理机械可清引用并删除文件")
        return 0

    # 原子性：先全量判定，任一引用非机械可清 → 完全不动（不产生部分
    # 提交状态），列人工清单返回 1。全部可清才落盘。
    removable, manual = _judge_removable(root, _refs_by_file(refs), target_doc)
    if manual:
        print(f"[delete] 以下 {len(manual)} 处引用非机械可清，请人工处理后再删：")
        _print_refs(manual)
        print("[delete] 未做任何改动（原子拒绝，避免部分提交状态）")
        return 1

    _drop_lines(root, removable)
    os.remove(target_path)
    print(f"[delete] 已删除 {target_doc}（同步清理 {len(removable)} 个引用文件）")
    print("[delete] 请 git add -A && python policy/check_doc_refs.py 验证")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doc_sync",
        description="文档调用点同步层：refs/rename/delete（默认 dry-run）",
    )
    parser.add_argument("--root", default=None, help="扫描根目录（默认仓库根）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_refs = sub.add_parser("refs", help="列出某 docs 文件的引用点")
    p_refs.add_argument("target")

    p_ren = sub.add_parser("rename", help="改 docs 文件路径并同步引用点")
    p_ren.add_argument("old")
    p_ren.add_argument("new")
    p_ren.add_argument("--apply", action="store_true")

    p_del = sub.add_parser("delete", help="删除 docs 文件并清理引用")
    p_del.add_argument("target")
    p_del.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent

    if args.cmd == "refs":
        return _cmd_refs(root, args.target)
    if args.cmd == "rename":
        return cmd_rename(root, args.old, args.new, args.apply)
    if args.cmd == "delete":
        return cmd_delete(root, args.target, args.apply)
    return 1


if __name__ == "__main__":
    sys.exit(main())
