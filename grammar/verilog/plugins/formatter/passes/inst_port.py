"""inst_port.py — 模块实例化端口连接对齐 pass

结构：
    .port_name ( connection ),
    ────────── ─ ────────── ─ ─
      name       lp   expr   rp term

对齐目标：port_name / ( / connection / ) 四列。

依赖 grouping.py 的分组工具。
"""

from __future__ import annotations

import re

from ..boundary import LineContext
from ..grouping import group_by_scope


def run_inst_port_align(lines: list[str], contexts: list[LineContext]) -> list[str]:
    """对齐模块实例化端口连接行。

    匹配以 `.port_name(` 开头的行（实例端口连接），
    对同一 scope 深度内的连续实例端口做列对齐。
    """
    _PORT_RE = re.compile(
        r"^(\s*)"                              # 1: indent
        r"\.(\w[\w\[\]]*)"                     # 2: port name (after .)
        r"(\s*\(\s*)"                          # 3: opening paren + spaces
        r"([^,;]*?)"                           # 4: connection expression
        r"(\s*\))"                             # 5: closing paren + spaces
        r"(\s*,?\s*)"                          # 6: terminator + trailing
        r"$"
    )

    result = list(lines)

    def match_fn(line: str) -> bool:
        return bool(_PORT_RE.match(line))

    groups = group_by_scope(lines, contexts, match_fn, break_distance=3)
    for group in groups:
        if len(group) < 2:
            continue
        # 收集各列
        rows = []
        for idx in group:
            m = _PORT_RE.match(result[idx])
            if not m:
                continue
            indent = m.group(1)
            name = "." + m.group(2)
            lp = m.group(3)
            expr = m.group(4)
            rp = m.group(5)
            term = m.group(6)
            rows.append((idx, indent, name, lp, expr, rp, term))

        if len(rows) < 2:
            continue

        max_name = max(len(r[2]) for r in rows)
        max_expr = max(len(r[4]) for r in rows)
        max_lp = max(len(r[3]) for r in rows)

        for idx, indent, name, lp, expr, rp, term in rows:
            padded_name = name + " " * (max_name - len(name))
            padded_lp = lp.rjust(max_lp) if lp.strip() else lp
            padded_expr = expr + " " * (max_expr - len(expr))
            result[idx] = indent + padded_name + padded_lp + padded_expr + rp + term

    return result
