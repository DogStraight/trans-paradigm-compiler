"""
列对齐 — 按语义列对齐。

从右向左推断各语义列位置。结构参考 grammar 中 Declarator / TypeSpec 定义：
  indent | first_token | opt_type | opt_range | name | opt_array_range | opt_init

终结符（, ;）保留在 name 或 array_range/init 中，不对齐。

依赖 boundary.py 提供的 RichLineContext 元数据 + grouping.py 分组工具。
"""

from __future__ import annotations

from typing import Any

from ..boundary import LineContext
from ..grouping import group_by_scope, extract_rows, compute_column_widths


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
    for ch in stripped:
        if ch == "[":
            in_bracket += 1
            buf.append(ch)
        elif ch == "]":
            in_bracket -= 1
            buf.append(ch)
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


def _extract_semantic(tokens: list[str]) -> list[str] | None:
    """从 token 列表提取语义列。

    Returns: [indent, first, opt_type, opt_range, name, opt_array_range, opt_init]
    无法可靠解析（一行多声明等）返回 None（调用方跳过，保留原文）。

    以顶层 `=` 定位 init（`=` 后整体保留），避免 `32'h ffff_ffff` 中
    `ffff_ffff` 被误判为 name 而丢真名（曾丢 LATCHED_IRQ/STACKADDR）。
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

    # 找顶层 =（圆括号/位拼接内忽略；方括号 `[...]` 已被 tokenize 合成单 token 无需 depth）
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

    # 声明部分去掉终结符
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
    return [indent, first, opt_type, opt_range, name, "", init, term]


def _join_semantic(cols: list[str], widths: list[int]) -> str:
    # 第 8 列为结尾终结符（,;），不参与对齐，直接追加
    term = cols[7] if len(cols) >= 8 else ""
    body = cols[1:7] if len(cols) >= 8 else cols[1:]
    parts = [cols[0]]
    for j, val in enumerate(body, start=1):
        if not val:
            parts.append(" " if 1 <= j <= 3 else "")
            continue
        w = widths[j] if j < len(widths) else 0
        # 只对齐前 3 列（first/opt_type/opt_range）；name 及之后紧跟
        # （ref 风格：类型/位宽列对齐 + name 紧跟，逗号/分号不被推到列尾）
        if j >= 4:
            parts.append(" " + val if val else "")
        elif j < 3:
            parts.append(val + " " * (w - len(val) + 1))
        else:
            parts.append(val + " " * (w - len(val)))
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
        # 用 _tokenize_bracket_aware + _extract_semantic 提取语义列
        extract_fn = lambda line: _extract_semantic(_tokenize_bracket_aware(line))  # noqa: E731
        rows, idxs = extract_rows(result, group, extract_fn)
        if len(rows) < 2:
            continue
        widths = compute_column_widths(rows, 5)
        for ri, cols in enumerate(rows):
            result[idxs[ri]] = _join_semantic(cols, widths)
    return result
