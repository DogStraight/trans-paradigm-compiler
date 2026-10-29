"""rewrite.py — 片段模式主编排：bytes → 岛树 → 岛管线 → 合成 → bytes。

契约（作者 2026-10-30 定稿，见 `docs/gaps/gap-fragment-mode.md`）：

- 岛 = 语法配置推导出的语法单元；**自顶向下**：节点过管线成功即整段替换、不再处理
  子节点；失败递归子节点；仍失败 ⇒ 该区间落 water；
- water 原样保留；无岛 / 零变化 ⇒ **逐字节**返回原 bytes（BOM/CRLF/无尾换行保真）；
- 后验默认开（岛级重解析 + 双跑逐字幂等，见 `process.format_island`）。

Doc: islands/README.md
"""

from __future__ import annotations

import difflib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from core.define import DEFAULT_RULES_DIR

from .model import IslandModel
from .process import format_island
from .segment import has_macro, line_indent, node_span, token_offsets
from .splice import apply_edits, reindent


@dataclass
class RewriteResult:
    original: bytes
    output: bytes
    processed: list[str] = field(default_factory=list)
    water: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.output != self.original


def _rule_name(node) -> str:
    return node.rule if isinstance(node.rule, str) else "/".join(node.rule)


def _collect(
    source: str,
    tokens,
    offsets: list[int],
    nodes,
    rules_dir: str,
    ext_dirs: list[str] | None,
) -> tuple[list[tuple[int, int, str]], list[str], int]:
    """递归收集岛编辑：自顶向下，成功即停；返回 (edits, processed, water 计数)。"""
    edits: list[tuple[int, int, str]] = []
    processed: list[str] = []
    water = 0

    def walk(node) -> bool:
        nonlocal water
        span = node_span(source, tokens, offsets, node)
        if span is None:
            return False
        if has_macro(tokens, node):
            # 含宏区间：整节点落水，但子节点可能不含宏——继续尝试子节点
            for child in node.children:
                walk(child)
            water += 1
            return False
        out = format_island(source[span[0] : span[1]], rules_dir, ext_dirs)
        if out is not None:
            indent = line_indent(source, span[0])
            edits.append((span[0], span[1], reindent(out.rstrip("\n"), indent)))
            processed.append(_rule_name(node))
            return True
        handled = False
        for child in node.children:
            if walk(child):
                handled = True
        if not handled:
            water += 1
        return handled

    for node in nodes:
        walk(node)
    return edits, processed, water


def rewrite_bytes(
    data: bytes,
    rules_dir: str = DEFAULT_RULES_DIR,
    ext_dirs: list[str] | None = None,
) -> RewriteResult:
    """bytes → bytes（identity 以 bytes 比较；无岛/零变化逐字节返回原 bytes）。"""
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    model = IslandModel(rules_dir, ext_dirs)
    tokens = model.tokenize(text)
    nodes = model.discover(tokens)
    offsets = token_offsets(text, tokens)
    edits, processed, water = _collect(
        text, tokens, offsets, nodes, rules_dir, model.ext_dirs
    )
    if not edits:
        return RewriteResult(original=data, output=data, processed=[], water=water)
    out_text = apply_edits(text, edits)
    out_bytes = out_text.encode("utf-8")
    if bom:
        out_bytes = b"\xef\xbb\xbf" + out_bytes
    return RewriteResult(
        original=data, output=out_bytes, processed=processed, water=water
    )


def rewrite_file(
    path: str | Path,
    rules_dir: str = DEFAULT_RULES_DIR,
    write: bool = False,
    ext_dirs: list[str] | None = None,
) -> RewriteResult:
    p = Path(path)
    data = p.read_bytes()
    result = rewrite_bytes(data, rules_dir, ext_dirs)
    if write and not result.errors and result.changed:
        p.write_bytes(result.output)
    return result


def print_diff(name: str, result: RewriteResult) -> None:
    """dry-run diff + 摘要（processed / water / 变化与否）。"""
    a = result.original.decode("utf-8-sig").splitlines(keepends=True)
    b = result.output.decode("utf-8-sig").splitlines(keepends=True)
    sys.stdout.writelines(
        difflib.unified_diff(
            a, b, fromfile=f"{name} (original)", tofile=f"{name} (rewritten)"
        )
    )
    print(
        f"# {name}: 岛 {len(result.processed)} 个已处理，water {result.water} 处，"
        f"{'已改写' if result.changed else '未变化'}"
    )
