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

from typing import Any

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


def _is_comment_or_directive(line: str, is_directive: bool = False) -> bool:
    s = line.lstrip()
    if s.startswith("//") or s.startswith("/*") or s.startswith("*"):
        return True
    if s.startswith("`"):
        # 指令（`ifdef/`define 等，boundary 配置推导）不折——折了改变宏体/
        # 条件结构；非指令宏调用语句（`LUI: $display(...)`）可折。无 contexts
        # 时保守视为指令（不折）。
        return is_directive
    return False


def _is_block_header(line: str) -> bool:
    """块头行：if/else if/for/while/case 等控制流条件行。

    块头条件在 `()` 内，折行时括号内断点允许（条件整体是括号包裹的表达式，
    `_top_level_split_points` 默认排除括号内——块头特殊放行，否则无断点可折）。
    识别用行首关键字 + 后随 `(` 条件，不硬编码语言知识之外的东西（关键字
    集合即控制流语句头，与 boundary 的 stmt_headers 同源）。
    """
    s = line.lstrip()
    if s.startswith(("else ", "else\t")) and "if" in s.split()[:3]:
        return True
    # `end else if (...)`（Verilog 同行 else 链）：end 收块 + else if 续条件
    if s.startswith("end") and "else if" in s:
        return True
    first = s.split()[0] if s else ""
    return (
        first in ("if", "else", "for", "while", "case", "casex", "casez") and "(" in s
    )


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
        elif ch == "/" and not in_str and i + 1 < len(line) and line[i + 1] == "/":
            return line[:i].rstrip(), line[i:]
    return line.rstrip(), ""


def _top_level_split_points(
    line: str,
    hints: list[str],
    allow_in_parens: bool = False,
    allow_concat: bool = False,
) -> list[int]:
    """返回行内断点位置列表（含运算符本身起始）。

    默认只在顶层（括号外）找断点；allow_in_parens=True（块头行）时括号内
    运算符也计入——`if (A && B || C) begin` 的条件整体在 `()` 内，顶层
    无断点可折，块头需在条件括号内折（条件本身是括号包裹表达式，折行
    不破坏结构，pratt 跳 newline 已支持）。

    括号深度语义（按危险度分级）：
      - `[]`（位选择 `[31:25]`）：内部 `:`/`,` 是分隔符不是运算符，任何
        断点都危险 → 永远排除。
      - `{}`（concat/replicate）：内部 `,` 是分隔符（元素间逗号）——
        默认排除（断裂破坏元素边界）；allow_concat=True（AST 确认语句
        完整）时放行——concat 元素是子表达式，折行可接受。
      - `()`（普通括号/函数调用/三目组）：内部运算符是表达式一部分，断点
        安全（pratt 跳 newline 已支持）→ allow_in_parens 时计入。
    """
    stripped = line.lstrip()
    base = len(line) - len(stripped)
    points: list[int] = []
    depth = 0  # () 深度
    bracket_depth = 0  # [] 深度
    brace_depth = 0  # {} 深度
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
        elif ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
        elif bracket_depth == 0 and (depth == 0 or allow_in_parens):
            for h in hints:
                if stripped.startswith(h, i):
                    # concat `{}` 内逗号是元素分隔符：默认排除（断裂破坏
                    # 元素边界）；allow_concat（AST 确认语句完整）放行
                    if brace_depth > 0 and h == "," and not allow_concat:
                        continue
                    points.append(base + i)
                    i += len(h) - 1
                    break
        i += 1
    return points


def _parse_line(parser: Any, src: str):
    """用 parser 解析单行包装文本，失败返回 None。

    parser 是管线复用的实例（format_generated 传入），带 lexer 绑定。
    解析失败（续行片段、单行不成语句）是 wrap 的预期回退路径——静默
    stderr（parser 的 WARN/failure-report 对 wrap 无诊断价值，刷屏干扰）。
    """
    try:
        lexer = getattr(parser, "lexer", None)
        if lexer is None:
            return None
        tokens = lexer.tokenize(src)
        import contextlib
        import io as _io

        with contextlib.redirect_stderr(_io.StringIO()):
            ast = parser.parse(tokens)
        if ast is None or getattr(parser, "_parse_truncated", False):
            return None
        return ast
    except Exception:  # noqa: BLE001
        return None


def _break_candidates(
    line: str, penalties: dict, parser: Any = None
) -> list[tuple[int, int]]:
    """收集所有断点候选，每个带断点惩罚值。

    断点取"运算符之后"（运算符留在第一行尾，续行从操作数开始）——
    parser 的 pratt 表达式不接受运算符行首续行（`&&`/`+` 行首解析失败），
    但接受运算符行尾 + 操作数行首（实测 0 错）。boundary 用"行尾运算符"
    识别续行（见 op_cont），indent 保缩进。

    parser：可选，语法感知——解析成功（AST 确认是完整语句）时 concat `{}`
    顶层逗号也放行（元素是子表达式，可断）；解析失败回退启发式（concat
    逗号仍排除，保守）。

    Returns: [(断点位置, 断点惩罚), ...] 位置升序。
    """
    ast_ok = bool(parser) and bool(_parse_line(parser, _wrap_line_src(line)))
    # 三目链中间行（行尾 `:`/`,` 且含 `?`）语义已由结构确认（续接下一分支），
    # concat `{}` 逗号放行——否则断点全在 concat 内被禁，行无法折
    is_ternary_cont = _is_ternary_cont_line(line)
    allow_concat = ast_ok or is_ternary_cont
    cands: list[tuple[int, int]] = []
    for h in _BREAK_HINTS:
        kind = _BREAK_KIND[h]
        for p in _top_level_split_points(
            line, [h], allow_in_parens=True, allow_concat=allow_concat
        ):
            cands.append((p + len(h), penalties.get(kind, 10)))
    # 三目 `:` 断点（`?` 后断会续行行首 `:` 非法；`:` 断在冒号后，冒号留行尾）
    for p in _top_level_split_points(
        line, [":"], allow_in_parens=True, allow_concat=allow_concat
    ):
        cands.append((p + 1, penalties.get("ternary", 30)))
    cands.sort(key=lambda c: c[0])
    return cands


def _is_ternary_cont_line(line: str) -> bool:
    """三目链中间行：行尾 `:`/`,` 且行内含 `?`（续接下一分支的链段）。

    这类行单行解析通常失败（未闭合三目），但结构语义已由行尾分隔符确认；
    wrap 放行其内部断点（嵌套三目/concat 逗号），续行仍以 `:`/`,` 结尾链不破。
    """
    code, _ = _split_trailing_comment(line)
    return (
        code.rstrip().endswith((":", ",")) and "?" in code
    )


def _wrap_line_src(line: str) -> str:
    """构造单行解析包装文本（module 壳 + 该行）。"""
    return "module m;\n" + line + "\nendmodule\n"


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
    parser = None,
) -> int | None:
    """选总惩罚最小的断点（Verible 惩罚模型，替代最右贪心）。

    对每个候选断点评估：断点惩罚 + 首行超列惩罚 + 尾行超列惩罚。
    尾行超列加重（×2）——尾行还可能继续折，超列更伤。选总惩罚最小者；
    并列时取更靠右的（保留更长前缀，更保守）。
    """
    stripped = line.lstrip()
    indent = _indent_of(line)
    cont_indent = indent + " " * indent_width
    cands = _break_candidates(line, penalties, parser=parser)
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
    parser: Any = None,
) -> list[str]:
    """折行：超宽行在惩罚最小断点拆成多行（贪婪拆到尾行 ≤ 宽，保证幂等）。

    续行缩进与 boundary 的 multi_line_cont 语义一致：折行发生在"本行是续行"
    （contexts 的 multi_line_cont，已从语句头折出）时，续行应同级（对齐语句头
    +4 的效果 = 本行缩进），不再 +4——否则续行再折会逐级递增（once 20 vs
    twice 16 漂移：`cond) && A && B;` 的续行 `B;` wrap 给 16+4=20，二次
    format boundary 按语句头重排给 16）。

    parser：可选，语法感知断点——对超宽行现场解析拿 AST 断点（ConcatExpr
    逗号/调用参数逗号/位选择内部可断不可断，全由 AST 结构推导）。解析输入
    就是该行文本，AST 节点 → 字符偏移与行内位置同源，无渲染错位问题。
    未传入/解析失败回退文本括号启发式。
    """
    if penalties is None or over_column is None:
        penalties, over_column = _load_wrap_config()
    out: list[str] = []
    for i, line in enumerate(lines):
        is_cont = i < len(contexts) and contexts[i].multi_line_cont
        is_directive = i < len(contexts) and contexts[i].is_directive
        out.extend(
            _wrap_line(
                line,
                max_width,
                indent_width,
                penalties,
                over_column,
                already_cont=is_cont,
                parser=parser,
                is_directive=is_directive,
            )
        )
    return out


def _wrap_line(
    line: str,
    max_width: int,
    indent_width: int = 4,
    penalties: dict | None = None,
    over_column: int | None = None,
    already_cont: bool = False,
    parser: Any = None,
    is_directive: bool = False,
) -> list[str]:
    """折单行：循环拆到每段 ≤ max_width。尾行缩进 = 语句头缩进 + 1 级。

    already_cont：本行已是续行（从语句头折出）→ 续行同级（对齐语句头 +4 的
    效果 = 本行缩进），不再 +4（防逐级递增）。

    is_directive：本行是预处理指令（`ifdef/`define 等，boundary 配置推导）。
    指令行不折（折了改变宏体/条件）；宏调用语句（行首反引号宏 + `(`，
    如 `` `LUI: $display(...) ``）可折——其参数在 `()` 内，断点安全。
    """
    if penalties is None or over_column is None:
        penalties, over_column = _load_wrap_config()
    # 不折的行：空/注释/指令/端口/声明（assign 除外）
    if len(line) <= max_width:
        return [line]
    stripped = line.lstrip()
    if not stripped:
        return [line]
    if _is_comment_or_directive(line, is_directive=is_directive):
        return [line]
    first = stripped.split()[0] if stripped.split() else ""
    if first in ("input", "output", "inout"):
        return [line]  # 端口列表不折
    # 分离行尾注释：分号判据、声明 `=` 判据都在代码部分做（注释内容不干扰），
    # 折出的行注释跟尾行（注释不折，但随语句语义位置走）
    code_part, trailing = _split_trailing_comment(line)
    is_header = _is_block_header(line)
    if first in ("reg", "wire", "parameter", "localparam"):
        # 声明：含 `=`（带初始化表达式）才折——`reg [31:0] x;` 无 = 不折
        if "=" not in code_part:
            return [line]
    # 已有续行（无分号结尾）不折——已由前面的 wrap 处理；
    # 块头行例外：if/for/while/case 无分号，条件在 `()` 内可折（断点含括号内）
    # 三目链中间行例外：行尾 `:`（如 `wire x = A ? {B, C} :` 续接下一分支）——
    # 折在行内嵌套三目 `? :` 或 concat 逗号处，续行仍以 `:`/`,` 结尾链不破
    # （pratt 跳 newline 已支持，实测解析 OK）；不折则整行超宽永久保留
    is_ternary_cont = _is_ternary_cont_line(line)
    if (
        not is_header
        and not is_ternary_cont
        and not code_part.rstrip().endswith(";")
    ):
        return [line]

    indent = _indent_of(line)
    # 续行 +1 级；本行已是续行 → 同级（对齐语句头 +4 的效果）
    cont_indent = indent if already_cont else indent + " " * indent_width

    # 分段折行：每轮折"最宽段"（含首段），直到所有段 ≤ max_width 或无断点。
    # 后续段将带 cont_indent（折出的行带续行缩进）——段宽判断含缩进，否则
    # 100 字符尾行 +4 缩进 = 104 仍超宽（darkriscv 三目链尾行）。
    # 首段 cur 已含原缩进（code_part = 原行去注释，含缩进），不加；
    # 折出的新段无缩进，判断 +len(cont_indent)。
    segments: list[str] = [code_part]
    guard = 0
    while guard < 8:
        guard += 1
        # 找最宽段（后续段带 cont_indent）
        def _seg_len(s: str, idx: int) -> int:
            return len(s) + len(trailing) + (len(cont_indent) if idx > 0 else 0)

        widest = max(range(len(segments)), key=lambda i: _seg_len(segments[i], i))
        if _seg_len(segments[widest], widest) <= max_width:
            break
        cur = segments[widest]
        pt = _find_break_point(cur, max_width, penalties, over_column, indent_width, parser=parser)
        if pt is None:
            break
        # 拆：分号移尾行（分号只属于最后一段；中间段无分号）
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
        # concat 内元素对齐空格清理：品类对齐对 concat 元素（`{ 16'bx ,`）
        # 误加列对齐空格（concat 元素非对齐组）——统一去逗号前多余空格
        # （`{ 16'bx ,` → `{ 16'bx,`），否则折点二次 format 漂移。
        # 只在含 concat `{` 的 head 做，避免误伤普通表达式
        if "{" in head and " ," in head:
            head = head.replace(" ,", ",")
        segments[widest : widest + 1] = [head, tail]
    result = segments
    # 行尾注释附回最后一行（代码语义位置 = 语句尾）
    if trailing:
        result[-1] = result[-1] + " " + trailing.lstrip()
    # 第一行保留原缩进，后续行用 cont_indent
    if len(result) > 1:
        result = [result[0]] + [cont_indent + r.lstrip() for r in result[1:]]
    return result
