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
# 逗号 < 逻辑 || && < 算术 + - < 乘除 * / < 三目 ? :
_BREAK_HINTS = [",", "||", "&&", "+", "-", "*", "/"]
# 断点类型映射：断点字符 → 惩罚类别（Verible 模型，惩罚低 = 更自然）
_BREAK_KIND = {
    ",": "comma",
    "||": "logic",
    "&&": "logic",
    "+": "arith",
    "-": "arith",
    "*": "arith",
    "/": "arith",
    ":": "ternary",
}

_DEFAULT_PENALTIES = {"comma": 1, "logic": 10, "arith": 20, "ternary": 30}
_DEFAULT_OVER_COLUMN = 10


def _load_wrap_config() -> tuple[dict, int]:
    """从 ConfigRegistry 读 [formatter.wrap]（语言包 tpc.toml）。

    Returns: (break_penalties, over_column_penalty)。缺省值保证无配置可用。
    """
    penalties = dict(_DEFAULT_PENALTIES)
    over = _DEFAULT_OVER_COLUMN
    try:
        from core.config_registry import ConfigRegistry
        cfg = ConfigRegistry.get("formatter.wrap")
        if isinstance(cfg, dict):
            bp = cfg.get("break_penalties")
            if isinstance(bp, dict):
                for k, v in bp.items():
                    if k in penalties:
                        penalties[k] = int(v)
            if "over_column_penalty" in cfg:
                over = int(cfg["over_column_penalty"])
    except Exception:
        pass
    return penalties, over


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _is_comment_or_directive(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("//") or s.startswith("/*") or s.startswith("`") or s.startswith("*")


def _split_trailing_comment(line: str) -> tuple[str, str]:
    """分离行尾 `//` 注释，返回 (代码部分, 注释部分含 `//`)。

    只在字符串外找 `//`。wrap 折行依赖它：
      - 分号判据：`wire x = ... ; // comment` 的注释挡住 `endswith(";")`
        （darkriscv 带注释声明超宽不折的根因）——判据应在代码部分做。
      - 折行后注释跟尾行（注释不折，但随语句语义位置走）。
    """
    in_str = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        elif (
            ch == "/"
            and not in_str
            and i + 1 < len(line)
            and line[i + 1] == "/"
        ):
            return line[:i].rstrip(), line[i:]
    return line.rstrip(), ""


def _top_level_split_points(line: str, hints: list[str]) -> list[int]:
    """返回行内顶层（括号外）断点位置列表（含运算符本身起始）。

    跟踪 () 与 [] 深度：位选择 `[31:25]` 内的 `:` 是三目符号但语义上是
    位选择分隔符，不算断点；[] 内其他运算符同样排除。
    """
    stripped = line.lstrip()
    base = len(line) - len(stripped)
    points: list[int] = []
    depth = 0
    bracket_depth = 0
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
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1
        elif depth == 0 and bracket_depth == 0:
            for h in hints:
                if stripped.startswith(h, i):
                    points.append(base + i)
                    i += len(h) - 1
                    break
        i += 1
    return points


def _break_candidates(line: str, penalties: dict) -> list[tuple[int, int]]:
    """收集所有顶层断点候选，每个带断点惩罚值。

    断点取"运算符之后"（运算符留在第一行尾，续行从操作数开始）——
    parser 的 pratt 表达式不接受运算符行首续行（`&&`/`+` 行首解析失败），
    但接受运算符行尾 + 操作数行首（实测 0 错）。boundary 用"行尾运算符"
    识别续行（见 op_cont），indent 保缩进。

    Returns: [(断点位置, 断点惩罚), ...] 位置升序。
    """
    cands: list[tuple[int, int]] = []
    for h in _BREAK_HINTS:
        kind = _BREAK_KIND[h]
        for p in _top_level_split_points(line, [h]):
            cands.append((p + len(h), penalties.get(kind, 10)))
    # 三目 `:` 断点（`?` 后断会续行行首 `:` 非法；`:` 断在冒号后，冒号留行尾）
    for p in _top_level_split_points(line, [":"]):
        cands.append((p + 1, penalties.get("ternary", 30)))
    cands.sort(key=lambda c: c[0])
    return cands


def _over_penalty(seg: str, max_width: int, over: int, indent_extra: int = 0) -> int:
    """折后单行的超列惩罚：超出 max_width 的部分 × over 系数。"""
    over_len = len(seg) - max_width - indent_extra
    if over_len <= 0:
        return 0
    return over_len * over


def _find_break_point(
    line: str,
    max_width: int,
    penalties: dict,
    over: int,
    indent_width: int = 4,
) -> int | None:
    """选总惩罚最小的断点（Verible 惩罚模型，替代最右贪心）。

    对每个候选断点评估：断点惩罚 + 首行超列惩罚 + 尾行超列惩罚。
    尾行超列加重（×2）——尾行还可能继续折，超列更伤。选总惩罚最小者；
    并列时取更靠右的（保留更长前缀，更保守）。
    """
    stripped = line.lstrip()
    indent = _indent_of(line)
    cont_indent = indent + " " * indent_width
    cands = _break_candidates(line, penalties)
    if not cands:
        return None

    best_pos = -1
    best_pen = float("inf")
    # 从右向左遍历，`<` 保证并列时保留先遇到的（更右）断点——保留更长前缀
    for pos, bpen in reversed(cands):
        head = line[:pos].rstrip()
        tail = line[pos:].strip()
        if not head or not tail:
            continue
        # 尾行缩进后仍算超列（续行带 cont_indent）
        pen = bpen + _over_penalty(head, max_width, over)
        pen += 2 * _over_penalty(tail, max_width, over, indent_extra=len(cont_indent))
        if pen < best_pen:
            best_pen = pen
            best_pos = pos
    return best_pos if best_pos >= 0 else None


def run_wrap_pass(
    lines: list[str],
    contexts: list[LineContext],
    max_width: int = DEFAULT_MAX_WIDTH,
    indent_width: int = 4,
    penalties: dict | None = None,
    over_column: int | None = None,
) -> list[str]:
    """折行：超宽行在惩罚最小断点拆成多行（贪婪拆到尾行 ≤ 宽，保证幂等）。"""
    if penalties is None or over_column is None:
        penalties, over_column = _load_wrap_config()
    out: list[str] = []
    for line in lines:
        out.extend(_wrap_line(line, max_width, indent_width, penalties, over_column))
    return out


def _wrap_line(
    line: str,
    max_width: int,
    indent_width: int = 4,
    penalties: dict | None = None,
    over_column: int | None = None,
) -> list[str]:
    """折单行：循环拆到每段 ≤ max_width。尾行缩进 = 语句头缩进 + 1 级。"""
    if penalties is None or over_column is None:
        penalties, over_column = _load_wrap_config()
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
    # 分离行尾注释：分号判据、声明 `=` 判据都在代码部分做（注释内容不干扰），
    # 折出的行注释跟尾行（注释不折，但随语句语义位置走）
    code_part, trailing = _split_trailing_comment(line)
    if first in ("reg", "wire", "parameter", "localparam"):
        # 声明：含 `=`（带初始化表达式）才折——`reg [31:0] x;` 无 = 不折
        if "=" not in code_part:
            return [line]
    # 已有续行（无分号结尾）不折——已由前面的 wrap 处理
    if not code_part.rstrip().endswith(";"):
        return [line]

    indent = _indent_of(line)
    cont_indent = indent + " " * indent_width  # 续行 +1 级

    result: list[str] = []
    cur = code_part
    guard = 0
    # 超宽判断含行尾注释：代码部分可能 ≤100 但 +注释 >100（darkriscv 带注释声明），
    # 折行仍需进行；注释不参与拆（不折），只在最后附回尾行
    while len(cur) + len(trailing) > max_width and guard < 8:
        guard += 1
        pt = _find_break_point(cur, max_width, penalties, over_column, indent_width)
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
    # 行尾注释附回最后一行（代码语义位置 = 语句尾）
    if trailing:
        result[-1] = result[-1] + " " + trailing.lstrip()
    # 第一行保留原缩进，后续行用 cont_indent
    if len(result) > 1:
        result = [result[0]] + [cont_indent + r.lstrip() for r in result[1:]]
    return result
