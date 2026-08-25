"""suppress.py — tpc-check 诊断豁免注释（Verilator lint_off/lint_on 借鉴）。

模型生成 v 文本 → tpc-check 检查的场景：生成器知道自己哪里"故意非标"
（如非标缩进/长行），可在源码内联豁免注释，门禁不误伤。两种形态：

  区间豁免（仿 Verilator lint_off/lint_on 注释对）：
      /* tpc-check off WC001 */    ← 从此行起豁免
      ...（被豁免的诊断）
      /* tpc-check on */           ← 此行恢复检查（on 行本身不豁免）

  单行豁免（disable-line）：
      // tpc-check: disable-line N001   ← 仅豁免本行

规则列表为空 = 该处豁免全部诊断；非空 = 仅豁免列出的 code。
未闭合的 off 注释（无配对 on）宽容处理：豁免到文件尾。

实现是**输出层过滤**：不侵入 linter/analyzer 检查器，只按
(文件行号, 诊断 code) 过滤已产出的诊断列表。行号为 0-based
（与诊断 range.start.line 对齐）。

Doc: docs/references.md（Verilog 静态检查工具群：suppress 借鉴 Verilator）
"""

from __future__ import annotations

import re
from typing import Iterator, Mapping

# 单行闭合的区间开启注释：/* tpc-check off [rules] */
_OFF_RE = re.compile(r"/\*\s*tpc-check\s+off\b([^*]*?)\*/")
# 区间恢复注释：/* tpc-check on */
_ON_RE = re.compile(r"/\*\s*tpc-check\s+on\b[^*]*?\*/")
# 单行豁免注释：// tpc-check: disable-line [rules]
_LINE_RE = re.compile(r"//\s*tpc-check:\s*disable-line\b([^\n]*)")


def _parse_rules(spec: str) -> set[str] | None:
    """解析豁免注释里的规则列表；空（未写）→ None（全部豁免）。"""
    rules = {t for t in spec.split() if t}
    return rules or None


def build_suppress_map(text: str) -> dict[int, set[str] | None]:
    """扫描源码，产出 {行号(0-based): 豁免规则集 或 None(全部)}。

    区间豁免 [off 行, on 行) 内的每一行都豁免；未闭合的 off 豁免到文件尾。
    单行豁免只豁免注释所在行。同行的豁免合并（None 优先=全部豁免）。
    """
    lines = text.splitlines()
    suppress: dict[int, set[str] | None] = {}
    pending: tuple[int, set[str] | None] | None = None  # (off 行, 规则集)

    def _fill_interval(start: int, end: int, rules: set[str] | None) -> None:
        for ln in range(start, end):
            prev = suppress.get(ln)
            if rules is None or prev is None:
                # None 优先：任一侧"全部豁免"则整行全部豁免
                suppress[ln] = rules if prev is None else None
            else:
                suppress[ln] = prev | rules

    for idx, line in enumerate(lines):
        # 区分代码区/注释区：`//` 之后的 `/* tpc-check off */` 是被注释掉的
        # 文本，不构成指令（指令格式是约定，普通注释里不应写完整指令）
        pos = line.find("//")
        code_part = line[:pos] if pos >= 0 else line
        comment_part = line[pos:] if pos >= 0 else ""

        m = _ON_RE.search(code_part)
        if m and pending is not None:
            off_line, rules = pending
            _fill_interval(off_line, idx, rules)
            pending = None
            continue
        m = _OFF_RE.search(code_part)
        if m and pending is None:
            pending = (idx, _parse_rules(m.group(1)))
            continue
        m = _LINE_RE.search(comment_part)
        if m:
            rules = _parse_rules(m.group(1))
            prev = suppress.get(idx)
            if rules is None or prev is None:
                suppress[idx] = rules if prev is None else None
            else:
                suppress[idx] = prev | rules

    if pending is not None:
        off_line, rules = pending
        _fill_interval(off_line, len(lines), rules)
    return suppress


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


def iter_suppress_lines(text: str) -> Iterator[tuple[int, set[str] | None]]:
    """供调试/文档：逐条输出豁免指令（行号, 规则集）。"""
    for idx, line in enumerate(text.splitlines()):
        pos = line.find("//")
        code_part = line[:pos] if pos >= 0 else line
        comment_part = line[pos:] if pos >= 0 else ""
        m = _OFF_RE.search(code_part)
        if m:
            yield idx, _parse_rules(m.group(1))
        m = _LINE_RE.search(comment_part)
        if m:
            yield idx, _parse_rules(m.group(1))
