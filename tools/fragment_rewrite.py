"""片段变换 P0 原型（记号模式 / island rewrite）——独立 CLI。

**范围（P0）**：显式记号（行注释 `// tpc:fragment id=<id> begin` … `// tpc:fragment end`）
圈定区域；一条纯语法规则 `always @(*)` → `always @*`；默认 dry-run diff，`--write` 才落盘。
不做：不建 AST、不依赖 scope、不新增 TOML 段/能力位、不支持隐式锚点/嵌套/块注释记号。

**安全边界**：
- 记号只从 lexer 的 `comment` token 识别 ⇒ 字符串里的假记号不会被当作记号；
- 条件编译死分支里的记号按 `scan_directives` 的 condition_blocks `active` 标记排除；
- 显式开/闭单层配对；未闭合/嵌套/错配 ⇒ `FragmentError`，不落任何编辑；
- identity gate：无命中时**逐字节**返回原 bytes（LF/CRLF/BOM/无尾换行都不变）。

Doc: docs/gaps/gap-fragment-mode.md
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from core.token_protocol import COMMENT_TOKEN_TYPE
from lexer import Lexer
from lexer.comment_syntax import load_comment_syntax
from preprocessor._expand import scan_directives

DEFAULT_RULES_DIR = "grammar/verilog"
_MARKER_RE = re.compile(
    r"^tpc:fragment(?:\s+id=(?P<id>[\w.-]+))?\s+(?P<verb>begin|end)\s*$"
)


class FragmentError(Exception):
    """P0 记号/配对错误（fail-closed：不产生编辑）。"""


@dataclass
class RewriteResult:
    original: bytes
    output: bytes
    hits: int = 0
    edits: list[tuple[int, int, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.output != self.original


def _offsets(source: str) -> list[int]:
    """行首字符 offset（1-based 行号索引；兼容 LF/CRLF）。"""
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _char_span(source: str, token) -> tuple[int, int]:
    starts = _offsets(source)
    start = starts[token.line - 1] + token.column
    return start, start + len(str(token.content))


def _inactive_lines(source: str, rules_dir: str) -> set[int]:
    """条件编译死分支的行号集合（P0 水域）。"""
    try:
        blocks = scan_directives(source, rules_dir, source_path=None)[2]
    except Exception:  # 扫描失败 ⇒ 不静默改写（P0 fail-closed）
        raise FragmentError("条件指令扫描失败，拒绝片段改写") from None
    inactive: set[int] = set()
    for block in blocks:
        for branch in block.get("branches", []):
            if branch.get("active"):
                continue
            for line_no, _text in branch.get("lines", []):
                inactive.add(int(line_no))
    return inactive


def _line_comment_body(token, syntax) -> str | None:
    if token.type != COMMENT_TOKEN_TYPE:
        return None
    text = str(token.content)
    for start in syntax.line_starts:
        if text.startswith(start):
            return text[len(start) :].strip()
    return None


def _parse_markers(source: str, rules_dir: str, tokens=None) -> list[dict]:
    """扫描显式记号；返回 [{id, begin_tok, end_tok}]（单层配对）。"""
    syntax = load_comment_syntax(rules_dir)
    if syntax.line_start is None:
        raise FragmentError(f"语言包 {rules_dir} 未声明行注释，P0 不支持记号模式")
    inactive = _inactive_lines(source, rules_dir)
    if tokens is None:
        tokens = Lexer(rules_dir=rules_dir).tokenize(source)
    open_id: str | None = None
    open_tok = None
    regions: list[dict] = []
    for token in tokens:
        body = _line_comment_body(token, syntax)
        if body is None:
            continue
        m = _MARKER_RE.match(body)
        if not m:
            continue
        if token.line in inactive:
            continue  # 死分支：水域
        verb = m.group("verb")
        if verb == "begin":
            marker_id = m.group("id")
            if not marker_id:
                raise FragmentError(f"L{token.line}: begin 记号缺少 id")
            if open_id is not None:
                raise FragmentError(f"L{token.line}: 嵌套 begin（P0 只支持单层）")
            open_id, open_tok = marker_id, token
        else:
            if open_id is None:
                raise FragmentError(f"L{token.line}: end 没有对应 begin")
            regions.append({"id": open_id, "begin_tok": open_tok, "end_tok": token})
            open_id, open_tok = None, None
    if open_id is not None:
        assert open_tok is not None
        raise FragmentError(f"L{open_tok.line}: begin 未闭合")
    return regions


def _find_always_star_edits(
    source: str, tokens, start_idx: int, end_idx: int
) -> list[tuple[int, int, str]]:
    """规则：区域内 token 序列 `always @ ( * )` → 删除括号（`always @*`）。"""
    edits: list[tuple[int, int, str]] = []
    contents = [str(t.content) for t in tokens]
    i = start_idx
    while i < end_idx:
        if contents[i] == "always" and i + 4 < end_idx:
            if (
                contents[i + 1] == "@"
                and contents[i + 2] == "("
                and contents[i + 3] == "*"
                and contents[i + 4] == ")"
            ):
                lp_start, _ = _char_span(source, tokens[i + 2])
                _, rp_end = _char_span(source, tokens[i + 4])
                edits.append((lp_start, rp_end, "*"))
                i += 5
                continue
        i += 1
    return edits


def rewrite_bytes(data: bytes, rules_dir: str = DEFAULT_RULES_DIR) -> RewriteResult:
    """bytes → bytes（identity gate 以 bytes 比较；BOM/换行/尾换行保真）。"""
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    try:
        tokens = Lexer(rules_dir=rules_dir).tokenize(text)
        regions = _parse_markers(text, rules_dir, tokens)
    except FragmentError as exc:
        return RewriteResult(original=data, output=data, errors=[str(exc)])
    edits: list[tuple[int, int, str]] = []
    for region in regions:
        begin_idx = tokens.index(region["begin_tok"])
        end_idx = tokens.index(region["end_tok"])
        edits.extend(_find_always_star_edits(text, tokens, begin_idx + 1, end_idx))
    edits.sort()
    for (s1, e1, _), (s2, e2, _) in zip(edits, edits[1:]):
        if s2 < e1:
            return RewriteResult(
                original=data,
                output=data,
                edits=edits,
                errors=[f"片段编辑重叠：{s1}:{e1} 与 {s2}:{e2}"],
            )
    if not edits:
        return RewriteResult(original=data, output=data)
    out = text
    for start, end, replacement in reversed(edits):
        out = out[:start] + replacement + out[end:]
    out_bytes = out.encode("utf-8")
    if bom:
        out_bytes = b"\xef\xbb\xbf" + out_bytes
    return RewriteResult(original=data, output=out_bytes, hits=len(edits), edits=edits)


def rewrite_file(
    path: str | Path, rules_dir: str = DEFAULT_RULES_DIR, write: bool = False
) -> RewriteResult:
    p = Path(path)
    data = p.read_bytes()
    result = rewrite_bytes(data, rules_dir)
    if write and not result.errors and result.changed:
        p.write_bytes(result.output)
    return result


def _print_diff(name: str, result: RewriteResult) -> None:
    a = result.original.decode("utf-8-sig").splitlines(keepends=True)
    b = result.output.decode("utf-8-sig").splitlines(keepends=True)
    sys.stdout.writelines(
        difflib.unified_diff(
            a, b, fromfile=f"{name} (original)", tofile=f"{name} (rewritten)"
        )
    )
    print(
        f"# {name}: {result.hits} 处命中，{len(result.errors)} 个错误，"
        f"{'已改写' if result.changed else '未变化'}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="片段变换 P0（显式记号 + always @(*) 规则）"
    )
    ap.add_argument("file", help="源文件")
    ap.add_argument("--rules-dir", default=DEFAULT_RULES_DIR, help="语言包目录")
    ap.add_argument("--write", action="store_true", help="落盘（默认 dry-run diff）")
    args = ap.parse_args(argv)
    result = rewrite_file(args.file, args.rules_dir, args.write)
    _print_diff(args.file, result)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
