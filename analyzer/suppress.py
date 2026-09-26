"""suppress.py — tpc-check 诊断豁免注释（Verilator lint_off/lint_on 借鉴）。

模型生成 v 文本 → tpc-check 检查的场景：生成器知道自己哪里"故意非标"
（如非标缩进/长行），可在源码内联豁免注释，门禁不误伤。两种形态（下面是
verilog 形态；**注释标点来自语言包声明**，见 `lexer/comment_syntax.py`——
引擎不认识 `//` / `/* */`，yaml 写作 `# …`）：

  区间豁免（仿 Verilator lint_off/lint_on 注释对）：
      /* tpc-check off WC001 */    ← 从此行起豁免
      ...（被豁免的诊断）
      /* tpc-check on */           ← 此行恢复检查（on 行本身不豁免）

  单行豁免（disable-line）：
      // tpc-check: disable-line N001   ← 仅豁免本行

规则列表为空 = 该处豁免全部诊断；非空 = 仅豁免列出的 code。
未闭合的 off 注释（无配对 on）宽容处理：豁免到文件尾。
语言包未声明块注释 → 区间豁免形态不存在（不报错：那是能力边界，不是配置
error）；未声明行注释 → 单行豁免形态不存在。

实现是**输出层过滤**：不侵入 linter/analyzer 检查器，只按
(文件行号, 诊断 code) 过滤已产出的诊断列表。行号为 0-based
（与诊断 range.start.line 对齐）。

Doc: docs/references.md（Verilog 静态检查工具群：suppress 借鉴 Verilator）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from lexer.comment_syntax import CommentSyntax


@dataclass(frozen=True)
class _Directives:
    """三种豁免指令的编译模式；语言包未声明对应注释形态时该字段为 None。"""

    off: re.Pattern | None       # 区间开启：`tpc-check off [规则...]`
    on: re.Pattern | None        # 区间闭合：`tpc-check on`
    line: re.Pattern | None      # 单行豁免：`tpc-check: disable-line [规则...]`


def _compile_directives(syntax: CommentSyntax) -> _Directives:
    """按语言的注释形态编译三种豁免指令模式。

    指令**关键字**（`tpc-check`）是引擎侧工具名，不是语言知识；只有注释标点
    来自声明。未声明对应形态 → 该模式为 None（该形态不可用）。
    """
    off_re: re.Pattern | None = None
    on_re: re.Pattern | None = None
    line_re: re.Pattern | None = None
    if syntax.block_open and syntax.block_close:
        o = re.escape(syntax.block_open)
        c = re.escape(syntax.block_close)
        # 规则列表捕获到结束定界符前（负向环视，不假定 `*` 不出现在规则里）
        body = f"((?:(?!{c}).)*?)"
        off_re = re.compile(rf"{o}\s*tpc-check\s+off\b{body}{c}")
        on_re = re.compile(rf"{o}\s*tpc-check\s+on\b(?:(?!{c}).)*?{c}")
    if syntax.line_start:
        ls = re.escape(syntax.line_start)
        line_re = re.compile(rf"{ls}\s*tpc-check:\s*disable-line\b([^\n]*)")
    return _Directives(off=off_re, on=on_re, line=line_re)


def _parse_rules(spec: str) -> set[str] | None:
    """解析豁免注释里的规则列表；空（未写）→ None（全部豁免）。"""
    rules = {t for t in spec.split() if t}
    return rules or None


@dataclass
class _IntervalScan:
    """区间豁免扫描状态（跨行游标）。"""

    suppress: dict[int, set[str] | None] = field(default_factory=dict)
    pending: tuple[int, set[str] | None] | None = None  # (off 行, 规则集)


def build_suppress_map(
    text: str, syntax: CommentSyntax
) -> dict[int, set[str] | None]:
    """扫描源码，产出 {行号(0-based): 豁免规则集 或 None(全部)}。

    区间豁免 [off 行, on 行) 内的每一行都豁免；未闭合的 off 豁免到文件尾。
    单行豁免只豁免注释所在行。同行的豁免合并（None 优先=全部豁免）。
    syntax：语言包注释形态（豁免指令以注释形态书写）。

    指令优先级按行内顺序判定：先看 `on`（闭合区间）→ 再看 `off`（开启区间）
    → 最后看单行指令（只认注释区，见 `_split_code_comment`）。
    """
    dirs = _compile_directives(syntax)
    lines = text.splitlines()
    scan = _IntervalScan()

    for idx, line in enumerate(lines):
        _scan_directive_line(idx, line, syntax, dirs, scan)

    if scan.pending is not None:
        off_line, rules = scan.pending
        _fill_interval(scan.suppress, off_line, len(lines), rules)
    return scan.suppress


def _scan_directive_line(
    idx: int, line: str, syntax: CommentSyntax, dirs: _Directives, scan: _IntervalScan
) -> None:
    """单行指令扫描：`on` → `off` → 单行豁免，按此优先级。

    区间指令触发即返回（该行不再作单行豁免判定——同原 `continue` 语义）。
    """
    code_part, comment_part = _split_code_comment(line, syntax)
    if _try_close_interval(idx, code_part, dirs, scan):
        return
    if _try_open_interval(idx, code_part, dirs, scan):
        return
    _mark_disable_line(idx, comment_part, dirs, scan)


def _try_close_interval(
    idx: int, code_part: str, dirs: _Directives, scan: _IntervalScan
) -> bool:
    """`on` 指令：闭合未决区间 [off 行, 本行)，本行自身不豁免。"""
    if dirs.on is None or scan.pending is None:
        return False
    if not dirs.on.search(code_part):
        return False
    off_line, rules = scan.pending
    _fill_interval(scan.suppress, off_line, idx, rules)
    scan.pending = None
    return True


def _try_open_interval(
    idx: int, code_part: str, dirs: _Directives, scan: _IntervalScan
) -> bool:
    """`off` 指令：开启区间（已在区间内时忽略，交由 `on` 闭合）。"""
    if dirs.off is None or scan.pending is not None:
        return False
    m = dirs.off.search(code_part)
    if not m:
        return False
    scan.pending = (idx, _parse_rules(m.group(1)))
    return True


def _mark_disable_line(
    idx: int, comment_part: str, dirs: _Directives, scan: _IntervalScan
) -> None:
    """单行豁免：只认注释区（代码区出现指令文本 = 被注释掉，不构成指令）。"""
    if dirs.line is None:
        return
    m = dirs.line.search(comment_part)
    if not m:
        return
    scan.suppress[idx] = _merge_suppress(
        scan.suppress.get(idx), _parse_rules(m.group(1))
    )


def _fill_interval(
    suppress: dict[int, set[str] | None],
    start: int,
    end: int,
    rules: set[str] | None,
) -> None:
    """区间豁免 [start, end) 的每一行并入 rules（同行既有豁免合并）。"""
    for ln in range(start, end):
        suppress[ln] = _merge_suppress(suppress.get(ln), rules)


def _split_code_comment(line: str, syntax: CommentSyntax) -> tuple[str, str]:
    """行 → (代码区, 注释区)。

    行注释起始之后的 `off` 指令是**被注释掉的文本**，不构成指令（指令格式是
    约定，普通注释里不应写完整指令）：区间指令只认代码区，单行指令只认注释区。
    语言包未声明行注释起始符（`line_start` 空）→ 整行视作代码区。
    """
    if not syntax.line_start:
        return line, ""
    pos = line.find(syntax.line_start)
    if pos < 0:
        return line, ""
    return line[:pos], line[pos:]


def _merge_suppress(
    prev: set[str] | None, rules: set[str] | None
) -> set[str] | None:
    """同行豁免合并：任一侧 None（全部豁免）优先，否则取并集。

    `prev` 是 `dict.get` 的结果——**缺键与值为 None 同为 None**，故
    `prev is None` 一律按"该行先前无豁免"处理（沿用原实现语义，未改动）。
    """
    if rules is None or prev is None:
        return rules if prev is None else None
    return prev | rules

def apply_suppressions(
    diagnostics: list[dict], suppress_map: Mapping[int, set[str] | None]
) -> list[dict]:
    """按豁免表过滤诊断列表（无 range 的诊断不过滤——无法定位到行）。"""
    if not suppress_map:
        return diagnostics
    kept: list[dict] = []
    for d in diagnostics:
        r = d.get("range")
        if not r:
            kept.append(d)
            continue
        if r["start"]["line"] not in suppress_map:
            kept.append(d)
            continue
        rules = suppress_map[r["start"]["line"]]
        if rules is None or (d.get("code") or "") in rules:
            continue  # 被豁免（None = 全部豁免）
        kept.append(d)
    return kept
