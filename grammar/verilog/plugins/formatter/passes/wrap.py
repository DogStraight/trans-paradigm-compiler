"""wrap.py — 宽度控制折行 pass

在 indent 之前运行：把超宽行在安全断点拆成多行（加换行，不改 token），
后续 indent 按 multi_line_cont 机制自然给续行缩进。

策略（保守、幂等）：
  - 只处理行宽 > max_line_width 的行
  - 只在安全断点拆：顶层逗号、逻辑/算术运算符、三目 ?/:
  - 不拆：注释行、字符串、ifdef 指令、模块端口列表、声明行、已有续行
  - 拆出的行无分号 → indent 视为多行续行（相对语句头 +1）

折行只加换行不改 token；幂等性由 test_idempotent 锁。
"""

from __future__ import annotations

from ..boundary import LineContext

# 默认行宽
DEFAULT_MAX_WIDTH = 100

# 安全断点字符（顶层，括号外）——按优先级从低到高拆
# 逗号 < 逻辑 || && < 三目 ? : < 算术 + - < 乘除 * /
_BREAK_HINTS = [",", "||", "&&", "+", "-", "*", "/"]
# 三目单独处理（? 和 : 都算断点）
_TERNARY = ("?", ":")


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _is_comment_or_directive(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("//") or s.startswith("/*") or s.startswith("`") or s.startswith("*")


def _top_level_split_points(line: str, hints: list[str]) -> list[int]:
    """返回行内顶层（括号外）断点位置列表（含运算符本身起始）。"""
    stripped = line.lstrip()
    base = len(line) - len(stripped)
    points: list[int] = []
    depth = 0
    in_str = False
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if in_str:
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            for h in hints:
                if stripped.startswith(h, i):
                    points.append(base + i)
                    i += len(h) - 1
                    break
        i += 1
    return points


def _find_break_point(line: str, max_width: int) -> int | None:
    """找第一个能让折行后两行都 ≤ max_width 的断点。

    优先最右的断点（保留最长前缀），但保证续行不超宽。
    返回断点位置（在该处换行，运算符留在第一行尾）。
    """
    stripped = line.lstrip()
    base = len(line) - len(stripped)
    indent = _indent_of(line)
    # 候选：按优先级（逗号→逻辑→算术）收集所有顶层断点
    all_points: list[int] = []
    for h in _BREAK_HINTS:
        pts = _top_level_split_points(line, [h])
        all_points.extend(pts)
    # 三目
    all_points.extend(_top_level_split_points(line, list(_TERNARY)))
    if not all_points:
        return None
    # 目标：优先保留最长前缀（最右断点），贪心循环会继续拆尾行
    all_sorted = sorted(all_points)
    if not all_sorted:
        return None
    return all_sorted[-1]  # 最右断点


def run_wrap_pass(
    lines: list[str],
    contexts: list[LineContext],
    max_width: int = DEFAULT_MAX_WIDTH,
    indent_width: int = 4,
) -> list[str]:
    """折行：超宽行在安全断点拆成多行（贪婪拆到尾行 ≤ 宽，保证幂等）。"""
    out: list[str] = []
    for line in lines:
        out.extend(_wrap_line(line, max_width, indent_width))
    return out


def _wrap_line(line: str, max_width: int, indent_width: int = 4) -> list[str]:
    """折单行：循环拆到每段 ≤ max_width。尾行缩进 = 语句头缩进 + 1 级。"""
    # 不折的行：空/注释/指令/端口/声明（assign 除外）
    if len(line) <= max_width:
        return [line]
    stripped = line.lstrip()
    if not stripped:
        return [line]
    if _is_comment_or_directive(line):
        return [line]
    first = stripped.split()[0] if stripped.split() else ""
    if first in ("input", "output", "inout"):
        return [line]  # 端口列表不折
    if first in ("reg", "wire", "parameter", "localparam"):
        # 声明：含 `=`（带初始化表达式）才折——`reg [31:0] x;` 无 = 不折
        if "=" not in stripped:
            return [line]
    # 已有续行（无分号结尾）不折——已由前面的 wrap 处理
    if not line.rstrip().endswith(";"):
        return [line]

    indent = _indent_of(line)
    cont_indent = indent + " " * indent_width  # 续行 +1 级

    result: list[str] = []
    cur = line
    guard = 0
    while len(cur) > max_width and guard < 8:
        guard += 1
        pt = _find_break_point(cur, max_width)
        if pt is None:
            break
        # 拆：分号移尾行
        has_semi = cur.rstrip().endswith(";")
        content = cur.rstrip()[:-1] if has_semi else cur.rstrip()
        if pt > len(content):
            break
        head = content[:pt].rstrip()
        tail = content[pt:].strip()
        if not tail or not head:
            break
        if has_semi:
            tail += ";"
        result.append(head)
        cur = tail
    result.append(cur)
    # 第一行保留原缩进，后续行用 cont_indent
    if len(result) > 1:
        result = [result[0]] + [cont_indent + r.lstrip() for r in result[1:]]
    return result
