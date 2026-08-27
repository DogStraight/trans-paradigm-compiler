"""
列对齐 — 按语义列对齐。

从右向左推断各语义列位置。结构参考 grammar 中 Declarator / TypeSpec 定义：
  indent | first_token | opt_type | opt_range | name | opt_array_range | opt_init

终结符（, ;）保留在 name 或 array_range/init 中，不对齐。

依赖 boundary.py 提供的 RichLineContext 元数据 + grouping.py 分组工具。
"""

from __future__ import annotations

import re
from typing import Any

from ..boundary import LineContext
from ..grouping import group_by_scope, compute_column_widths


# 纯数字位宽 `[msb:lsb]`（高位数字右对齐用；含表达式/参数如 `[WIDTH-1:0]` 不匹配）
_RANGE_RE = re.compile(r"^\[(\d+):(\d+)\]$")


def _align_range_internal(rows: list[list[str]], col: int = 3) -> None:
    """组内位宽列内部右对齐（ref 风格：`[3:0]` 与 `[31:0]` 同组时 → `[ 3:0]`）。

    只补 msb 前空格，不改 token 内容；msb 全为单数字时不改动。
    """
    msb_width = 0
    for row in rows:
        r = row[col] if len(row) > col else ""
        m = _RANGE_RE.match(r)
        if m:
            msb_width = max(msb_width, len(m.group(1)))
    if msb_width <= 1:
        return
    for row in rows:
        if len(row) <= col:
            continue
        m = _RANGE_RE.match(row[col])
        if m:
            row[col] = "[%*s:%s]" % (msb_width, m.group(1), m.group(2))


def _build_matcher(cfg: dict) -> Any | None:
    if "first_token" in cfg:
        tokens = cfg["first_token"]
        if isinstance(tokens, str):
            tokens = [tokens]
        token_set = frozenset(tokens)
        return lambda line: _first_token(line) in token_set if _first_token(line) else False
    if "regex" in cfg:
        import re
        pattern = re.compile(cfg["regex"])
        return lambda line: bool(pattern.match(line.lstrip()))
    return None


def _first_token(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped:
        return None
    return stripped.split()[0]


def _tokenize_bracket_aware(line: str) -> list[str]:
    stripped = line.lstrip()
    indent = line[:len(line) - len(stripped)]
    if not stripped:
        return []
    tokens: list[str] = []
    buf: list[str] = []
    in_bracket = 0
    i = 0
    n = len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == "[":
            in_bracket += 1
            buf.append(ch)
        elif ch == "]":
            in_bracket -= 1
            buf.append(ch)
        elif ch == "=" and in_bracket == 0:
            # 连续等号（`==`/`===`）是单个运算符，不拆成多个 `=` token
            # （防 `a == b` 被拆成 `a = = b`，重组后破坏运算符语义）
            j = i
            while j < n and stripped[j] == "=":
                j += 1
            eq = stripped[i:j]
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(eq)
            i = j - 1
        elif ch in "(),;={}" and in_bracket == 0:
            # 结构符独立成 token（即使粘连，如 `ffff_ffff,` / `(expr` / `0}`）
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(ch)
        elif ch.isspace() and in_bracket == 0:
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        tokens.append("".join(buf))
    return [indent] + tokens


def _is_ident(tok: str) -> bool:
    """标识符：字母/下划线开头。数字字面量（32'h、'h、0x1F 等）不算。"""
    if not tok:
        return False
    return tok[0].isalpha() or tok[0] == "_"


def _is_multidecl(rest: list[str]) -> bool:
    """检测一行多声明/多端口（括号外逗号分隔多个标识符，如 `reg a, b;`、
    `input clk, resetn,`）。行尾终结符逗号（`param = 1,`）不算。

    当前语义列模型只支持单声明；多声明行直接跳过（保留原文），防丢名字。
    """
    depth = 0
    for k, t in enumerate(rest):
        if t in ("(", "{"):
            depth += 1
        elif t in (")", "}"):
            depth -= 1
        elif t == "," and depth == 0:
            # 逗号后还有非终结符内容 → 多声明
            for nxt in rest[k + 1:]:
                if nxt in (",", ";"):
                    continue
                return True
    return False


def _parse_decl_parts(rest: list[str]) -> tuple[str, str, str, str] | None:
    """解析声明侧（不含 first token）：返回 (opt_type, opt_range, name, init)。

    以顶层 `=` 定位 init（`=` 后整体保留），避免 `32'h ffff_ffff` 中
    `ffff_ffff` 被误判为 name 而丢真名（曾丢 LATCHED_IRQ/STACKADDR）。
    声明侧含拼接/复制表达式（`{a, b} = ...`）时无法可靠解析 → None。
    """
    eq_idx = -1
    depth = 0
    for k, t in enumerate(rest):
        if t in ("(", "{"):
            depth += 1
        elif t in (")", "}"):
            depth -= 1
        elif t == "=" and depth == 0:
            eq_idx = k
            break

    if eq_idx >= 0:
        decl = rest[:eq_idx]
        # init 保留 `=`（防 _join_semantic 重组丢等号）
        init = "= " + " ".join(rest[eq_idx + 1:]).strip()
    else:
        decl = rest
        init = ""

    # 声明侧含拼接/复制表达式（`assign {a, b} = ...`）：其逗号是表达式
    # 分隔符，不是多声明分隔——走本路径会把逗号当列分隔吞掉（曾毁掉
    # concat LHS 的 `{a, b}` → `{a  b}`，fidelity 0.95→0.33）。
    if "{" in decl or "}" in decl:
        return None

    # 声明侧含圆括号（net 声明的 drive/charge strength `(strong1, pull0)` /
    # `(small)`，nettypes 插件 A.2.2.2）：括号内是强度语义不是列语义，走本
    # 路径会把 `(strong1, pull0)` 拆坏（逗号粘连 token + name 误判）。
    # 跳过对齐保留原文。
    if "(" in decl or ")" in decl:
        return None

    d = [t for t in decl if t not in (",", ";")]
    # name = 最后一个标识符（从右往左）
    i = len(d) - 1
    while i >= 0 and not _is_ident(d[i]):
        i -= 1
    if i < 0:
        return None
    name = d[i]
    # name 右侧杂项（端口列表关闭 `)` 等）保留，并入 init 尾部（防丢）
    trailing = " ".join(d[i + 1:]).strip()
    if trailing:
        init = (init + " " + trailing).strip() if init else trailing
    i -= 1
    # 剩下的 → opt_type（保留所有非 range 修饰 token，如 `localparam integer`）/ opt_range
    opt_type = ""
    opt_range = ""
    for t in d[:i + 1]:
        if t.startswith("["):
            opt_range = t
        else:
            opt_type = (opt_type + " " + t).strip() if opt_type else t
    return opt_type, opt_range, name, init


def _extract_semantic(tokens: list[str]) -> list[str] | None:
    """从 token 列表提取语义列（单声明）。

    Returns: [indent, first, opt_type, opt_range, name, opt_array_range, opt_init]
    无法可靠解析（一行多声明等）返回 None（调用方跳过，保留原文）。

    多声明的逐单元对齐走 _extract_semantic_multi（P1.5：多声明品类对齐）。
    """
    if len(tokens) < 2:
        return None
    indent = tokens[0]
    first = tokens[1]
    rest = list(tokens[2:])

    # 注释行跳过（防 `// comment` 被当声明）
    if first.startswith("//"):
        return None

    # 结尾终结符（,;）独立保存，_join_semantic 重组时加回（防丢）
    term = ""
    while rest and rest[-1] in (",", ";"):
        term = rest.pop() + term

    if _is_multidecl(rest):
        return None

    parts = _parse_decl_parts(rest)
    if parts is None:
        return None
    opt_type, opt_range, name, init = parts
    return [indent, first, opt_type, opt_range, name, "", init, term]


def _extract_semantic_multi(tokens: list[str]) -> list[list[str]] | None:
    """提取一行的全部语义单元（P1.5 多声明品类对齐）。

    单声明 → [单组]（等价 _extract_semantic）；多声明 → 每声明一组：
    类型头（first/opt_type）只挂首单元，单元间 term 为逗号、行尾终结符
    归末单元，非首单元 indent 置空（重组时不重复缩进）。任一单元无法
    可靠解析 → 返回 None（整行跳过，保守防丢名字）。
    """
    if len(tokens) < 2:
        return None
    indent = tokens[0]
    first = tokens[1]
    rest = list(tokens[2:])

    if first.startswith("//"):
        return None

    if not _is_multidecl(rest):
        single = _extract_semantic(tokens)
        return [single] if single is not None else None

    term = ""
    while rest and rest[-1] in (",", ";"):
        term = rest.pop() + term

    # 顶层逗号切分声明单元（圆括号/位拼接内忽略——`(` 内逗号是表达式分隔）
    units: list[list[str]] = []
    depth = 0
    cur: list[str] = []
    for t in rest:
        if t in ("(", "{"):
            depth += 1
        elif t in (")", "}"):
            depth -= 1
        if t == "," and depth == 0:
            units.append(cur)
            cur = []
        else:
            cur.append(t)
    units.append(cur)

    # 尾注注释保护：`input clk, // 行内注释` / `reg a, /* c */ b;` 的注释
    # 不是声明单元——任一单元含注释 token（`//`/`/*` 起始）时整行跳过
    # （保留原文，与旧 _is_multidecl 跳过行为一致）；纯声明多声明行
    # （无注释）才参与逐单元对齐。
    for u in units:
        if any(t.startswith("//") or t.startswith("/*") for t in u):
            return None

    out: list[list[str]] = []
    n = len(units)
    for ui, unit in enumerate(units):
        if not unit:
            return None  # 空单元（连续逗号）→ 保守跳过整行
        parts = _parse_decl_parts(unit)
        if parts is None:
            return None
        opt_type, opt_range, name, init = parts
        u_first = first if ui == 0 else ""
        u_type = opt_type if ui == 0 else ""  # 类型头只挂首单元
        u_term = "," if ui < n - 1 else term
        out.append(
            [indent if ui == 0 else "", u_first, u_type, opt_range,
             name, "", init, u_term]
        )
    return out


def _join_semantic(cols: list[str], widths: list[int]) -> str:
    # 第 8 列为结尾终结符（,;），不参与对齐，直接追加
    term = cols[7] if len(cols) >= 8 else ""
    body = cols[1:7] if len(cols) >= 8 else cols[1:]
    parts = [cols[0]]
    for j, val in enumerate(body, start=1):
        w = widths[j] if j < len(widths) else 0
        # 前 3 列（first/opt_type/opt_range）对齐（空列补到列宽+分隔）；
        # name 列从"内容起点"（前 3 列后）开始但不填充自身，
        # 终结符（`,`/`;`）紧跟 name（ref 端口/声明的 name 起始列对齐风格）
        if j <= 3:
            if val:
                parts.append(val + " " * (w - len(val) + 1))
            else:
                parts.append(" " * (w + 1))
        elif j == 4:
            parts.append(val)
        else:
            parts.append(" " + val if val else "")
    if term:
        parts.append(term)
    return "".join(parts)


def run_category_pass(
    lines: list[str],
    contexts: list[LineContext],
    cfg: dict,
) -> list[str]:
    match_fn = _build_matcher(cfg.get("matcher", {}))
    if match_fn is None:
        return list(lines)
    break_distance = cfg.get("break_distance", 3)
    result = list(lines)

    groups = group_by_scope(lines, contexts, match_fn, break_distance)
    for group in groups:
        # 多单元提取（P1.5 多声明品类对齐）：多声明行拆多单元，全部单元
        # 参与列宽计算；同行的单元重组时拼回一行（" ".join）——首单元带
        # indent/类型头，后续单元 indent 为空，name 列同基准对齐
        row_groups: list[list[list[str]]] = []
        valid: list[int] = []
        for idx in group:
            units = _extract_semantic_multi(
                _tokenize_bracket_aware(result[idx])
            )
            if units:
                row_groups.append(units)
                valid.append(idx)
        if len(valid) < 2:
            continue
        rows = [cols for units in row_groups for cols in units]
        # 位宽列内部右对齐（`[3:0]` → `[ 3:0]`），与 ref 同组内对齐一致
        _align_range_internal(rows)
        widths = compute_column_widths(rows, 5)
        for gi, idx in enumerate(valid):
            joined = " ".join(
                _join_semantic(c, widths) for c in row_groups[gi]
            )
            result[idx] = joined
    return result
