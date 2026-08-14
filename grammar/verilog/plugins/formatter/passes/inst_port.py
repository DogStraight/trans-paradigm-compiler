"""inst_port.py — 模块实例化端口连接对齐 pass

结构：
    .port_name ( connection ),
    ────────── ─ ────────── ─ ─
      name       lp   expr   rp term

能力：
  1. 拆单行多端口（`.clk(clk), .resetn(resetn), ...` → 每行一个），括号平衡
  2. 连续端口行分组对齐 name / expr 两列（与 ref 格式一致）

不依赖 contexts（行号已由 indent pass 定好；拆分后行数变化）。
"""

from __future__ import annotations

import re

from ..boundary import LineContext

# 端口名：`.` + 标识符 + 可选 `(` 前空格（end 指向 `(`）
_PORT_NAME_RE = re.compile(r"\.(\w[\w\[\]]*)\s*\(")


def _port_parse(stripped: str, m) -> tuple[int, int, int, str] | None:
    """解析 `.name(` 端口段。括号平衡找匹配 `)`。

    Returns: (end, expr_start, expr_end, term)
        end       含尾随 `,`/`;` 的段结束位置（供拆分）
        expr_start/expr_end  expr 区间（exclusive，不含 `)`）
        term      尾随 `,` 或 `;`（可为空）
    非纯端口（`)` 后还有内容，如参数化实例化的 `) inst_name (`）返回 None。
    """
    i = m.end() - 1  # '('
    depth = 0
    expr_start = m.end()
    while i < len(stripped):
        if stripped[i] == "(":
            depth += 1
        elif stripped[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    expr_end = i  # 匹配 `)` 的位置（exclusive）
    end = i + 1
    term = ""
    if end < len(stripped) and stripped[end] in (",", ";"):
        term = stripped[end]
        end += 1
    elif end < len(stripped) and stripped[end:].strip():
        return None  # 后接其他内容 → 非纯端口段
    return (end, expr_start, expr_end, term)


def _split_line_ports(line: str) -> list[str] | None:
    """行内含多个 `.name(` → 拆成每行一个端口（括号平衡）。

    Returns: 新行列表（每行一个端口段），无多端口或含非纯端口段返回 None。
    """
    stripped = line.lstrip()
    indent = line[:len(line) - len(stripped)]
    ms = list(_PORT_NAME_RE.finditer(stripped))
    if len(ms) <= 1:
        return None
    segs = []
    for m in ms:
        parsed = _port_parse(stripped, m)
        if parsed is None:
            return None  # 含参数化实例化等非纯端口行 → 整行不拆（保安全）
        end, _, _, _ = parsed
        segs.append(indent + stripped[m.start():end].rstrip())
    return segs


def _match_port(line: str) -> tuple[str, str, str, str] | None:
    """解析单端口行 `.name(expr),`（括号平衡，支持嵌套）。

    Returns: (indent, name, expr, term) 或 None（非纯端口行）。
    """
    stripped = line.lstrip()
    indent = line[:len(line) - len(stripped)]
    m = _PORT_NAME_RE.match(stripped)
    if not m:
        return None
    parsed = _port_parse(stripped, m)
    if parsed is None:
        return None
    _, expr_start, expr_end, term = parsed
    expr = stripped[expr_start:expr_end].strip()
    return (indent, "." + m.group(1), expr, term)


def _is_port_line(line: str) -> bool:
    stripped = line.lstrip()
    m = _PORT_NAME_RE.match(stripped)
    if not m:
        return False
    return _port_parse(stripped, m) is not None


def _align_group(lines: list[str], group: list[int]) -> None:
    """对齐一组端口行的 name / expr 两列（ref 格式：`.name(...expr...),`）。

    缩进统一为组内最大缩进：原始渲染常让首端口行（实例声明行的续行）
    比后续端口行多一层缩进（如 `.clk` 12 / `.resetn` 8），ref 统一对齐。
    """
    rows = []
    for idx in group:
        m = _match_port(lines[idx])
        if m:
            rows.append((idx, m))
    if len(rows) < 2:
        return
    max_name = max(len(r[1][1]) for r in rows)
    max_expr = max(len(r[1][2]) for r in rows)
    max_indent = max(len(r[1][0]) for r in rows)
    for idx, (indent, name, expr, term) in rows:
        lines[idx] = " " * max_indent + name.ljust(max_name) + "(" + expr.ljust(max_expr) + ")" + term


def _align_contiguous_ports(lines: list[str]) -> None:
    """连续端口行分组对齐（组间按非端口行分隔）。"""
    i = 0
    n = len(lines)
    while i < n:
        if _is_port_line(lines[i]):
            group = [i]
            j = i + 1
            while j < n and _is_port_line(lines[j]):
                group.append(j)
                j += 1
            if len(group) >= 2:
                _align_group(lines, group)
            i = j
        else:
            i += 1


def run_inst_port_align(lines: list[str], contexts: list[LineContext]) -> list[str]:
    """拆单行多端口 + 连续端口行对齐。"""
    result: list[str] = []
    for line in lines:
        # impl 绑定语句（`impl type.role (ports)`）：`type.role` 会被当端口段拆开
        # （如 `impl spi.master (.clk(clk),` 拆成 `.master(.clk(clk),)` + `.clk(clk),`），
        # 整行跳过拆分——其后续 `.port(expr)` 行仍走连续端口对齐。
        if line.lstrip().startswith("impl "):
            result.append(line)
            continue
        segs = _split_line_ports(line)
        if segs is not None:
            result.extend(segs)
        else:
            result.append(line)
    _align_contiguous_ports(result)
    return result
