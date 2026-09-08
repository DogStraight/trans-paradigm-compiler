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
class Ref:
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


def collect_refs(root: Path, target: str) -> list[Ref]:
    """收集引用 target（docs 相对路径）的全部引用点。

    同一组正则与 check_doc_refs 完全一致：_DOC_HEADER_RE（代码 Doc: 头）、
    _DOC_LINK_RE（docs/ 链接形态）、_BARE_REF_RE（反引号裸名/子目录前缀）。
    区间重叠去重：`./docs/x.md` 内嵌的 `docs/x.md`、Doc: 头行内的路径
    片段不重复计数（保留先收集的最长/最早区间）。
    """
    refs: list[Ref] = []
    target = target.replace("\\", "/").lstrip("./")
    if not target.startswith("docs/"):
        target = f"docs/{target}"

    for rel in _iter_scan_files(root):
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        code_blocks = _md_codeblock_ranges(text) if rel.suffix == ".md" else []
        is_code = rel.suffix == ".py"
        collected: list[tuple[int, int, Ref]] = []  # (start, end, ref) 供重叠判断

        def overlaps(start: int, end: int) -> bool:
            return any(s < end and start < e for s, e, _ in collected)

        def add(start: int, end: int, text_val: str, tgt: str, full: str) -> None:
            if overlaps(start, end):
                return
            collected.append((start, end, Ref(rel.as_posix(), _line_of(text, start),
                                              start, end, text_val, tgt or "")))

        # 形态 1：代码 Doc: 头（整行匹配，替换区间 = group(1) 路径部分）。
        # .py 对 docs 的引用只有 Doc: 头这一种形态（仓库 114 处实证）——
        # 代码字符串/注释里的 docs/ 路径是数据或叙述，不是引用，不收集
        # （避免 rename 误伤测试夹具）。
        if is_code:
            for m in gate._DOC_HEADER_RE.finditer(text):
                tgt = m.group(1)
                if tgt != target:
                    continue
                add(m.start(1), m.end(1), m.group(0).strip(), tgt, m.group(0))

        # 形态 2/3 仅对 .md/.toml（导航索引/文档正文/TOML 注释）
        if not is_code:
            # 形态 2：docs/ 链接形态（README ./docs/...、正文 docs/...）
            for m in gate._DOC_LINK_RE.finditer(text):
                if any(s <= m.start() < e for s, e in code_blocks):
                    continue
                tgt = gate._resolve_nav_target(m.group(0), root)
                if tgt != target:
                    continue
                add(m.start(), m.end(), m.group(0), tgt, m.group(0))

            # 形态 3：反引号裸名 / 子目录前缀（替换区间 = group(1) 内部，保留反引号）
            for m in gate._BARE_REF_RE.finditer(text):
                if any(s <= m.start() < e for s, e in code_blocks):
                    continue
                cand = m.group(1)
                if "docs/" in text[max(0, m.start() - 8): m.end()]:
                    continue  # 同一引用已按完整路径形态处理
                tgt = gate._resolve_nav_target(cand, root)
                if tgt != target:
                    continue
                add(m.start(1), m.end(1), cand, tgt, cand)
        refs.extend(r for _, _, r in collected)
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


def _replacement_for(ref: Ref, new_doc: str) -> str | None:
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


def _apply_replacements(root: Path, refs: Sequence[Ref], new_doc: str) -> list[Ref]:
    """按引用点做文本替换；返回无法机械处理的引用（人工清单）。

    按文件聚合、从后往前替换（避免区间漂移）；仅 --apply 调用。
    """
    manual: list[Ref] = []
    by_file: dict[str, list[Ref]] = {}
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

def _print_refs(refs: Sequence[Ref], root: Path) -> None:
    if not refs:
        print("  无引用点（可直接改名/删除）")
        return
    print(f"  引用点 {len(refs)} 处：")
    for ref in sorted(refs, key=lambda r: (r.path, r.line)):
        print(f"      {ref.path}:{ref.line}  {ref.text}")


# ── 子命令 ──────────────────────────────────────────────────────────────────

def cmd_refs(root: Path, target: str) -> int:
    print(f"[refs] {target} 的引用点：")
    _print_refs(collect_refs(root, target), root)
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
    _print_refs(refs, root)
    if not apply:
        print("[rename] dry-run：加 --apply 落盘；落盘后请 git add -A 并跑 check_doc_refs.py 验证")
        return 0

    manual = _apply_replacements(root, refs, new_doc)
    if manual:
        print(f"[rename] 以下 {len(manual)} 处无法机械替换，请人工处理：")
        _print_refs(manual, root)
    # 移动文件本身
    os.makedirs(old_path.parent, exist_ok=True)
    new_path = root / new_doc
    os.makedirs(new_path.parent, exist_ok=True)
    os.replace(old_path, new_path)
    print(f"[rename] 已移动 {old_doc} → {new_doc}")
    print("[rename] 请 git add -A && python policy/check_doc_refs.py 验证")
    return 0


def cmd_delete(root: Path, target: str, apply: bool) -> int:
    target_doc = target.replace("\\", "/").lstrip("./")
    if not target_doc.startswith("docs/"):
        target_doc = f"docs/{target_doc}"
    target_path = root / target_doc
    if not target_path.is_file():
        print(f"[delete] 目标不存在: {target_doc}")
        return 1

    refs = collect_refs(root, target_doc)
    print(f"[delete] {target_doc} 的引用点 {len(refs)} 处：")
    _print_refs(refs, root)
    if not apply:
        print("[delete] dry-run：加 --apply 清理机械可清引用并删除文件")
        return 0

    # 原子性：先全量判定，任一引用非机械可清 → 完全不动（不产生部分
    # 提交状态），列人工清单返回 1。全部可清才落盘。
    # 机械可清判定：
    # - 代码 Doc: 头行（整行删）
    # - 独占表格/列表行（行内除本引用外无其它 .md 引用 → 整行删）
    # 行内并列引用 → 人工。
    manual: list[Ref] = []
    by_file: dict[str, list[Ref]] = {}
    for ref in refs:
        by_file.setdefault(ref.path, []).append(ref)

    # 阶段 1：判定（只读，不落盘）
    removable: dict[str, list[int]] = {}  # rel -> [line_idx 集合（0-based）]
    for rel, file_refs in by_file.items():
        path = root / rel
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        is_py = rel.endswith(".py")
        for ref in sorted(file_refs, key=lambda r: r.start, reverse=True):
            line_idx = ref.line - 1
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]
            if is_py and gate._DOC_HEADER_RE.search(line):
                removable.setdefault(rel, []).append(line_idx)
                continue
            if not is_py and not _other_md_refs(root, line, target_doc):
                removable.setdefault(rel, []).append(line_idx)
                continue
            manual.append(ref)
    if manual:
        print(f"[delete] 以下 {len(manual)} 处引用非机械可清，请人工处理后再删：")
        _print_refs(manual, root)
        print("[delete] 未做任何改动（原子拒绝，避免部分提交状态）")
        return 1

    # 阶段 2：落盘（按行号倒序删行，防区间漂移）
    for rel, line_idxs in removable.items():
        path = root / rel
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for line_idx in sorted(set(line_idxs), reverse=True):
            del lines[line_idx]
        path.write_text("".join(lines), encoding="utf-8")

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
        return cmd_refs(root, args.target)
    if args.cmd == "rename":
        return cmd_rename(root, args.old, args.new, args.apply)
    if args.cmd == "delete":
        return cmd_delete(root, args.target, args.apply)
    return 1


if __name__ == "__main__":
    sys.exit(main())
