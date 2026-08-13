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
        elif ch.isspace() and in_bracket == 0:
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return [indent] + tokens


def _extract_semantic(tokens: list[str]) -> list[str] | None:
    """从 token 列表提取语义列。

    Returns: [indent, first, opt_type, opt_range, name, opt_array_range, opt_init]
    """
    if len(tokens) < 2:
        return None
    indent = tokens[0]
    first = tokens[1]
    i = len(tokens) - 1
    # 跳过独立终结符
    if i > 1 and tokens[i] in (",", ";"):
        i -= 1
    # 收集等号右侧（init + array_range mixed）
    right_parts = []
    while i > 1 and not tokens[i][0].isalpha():
        right_parts.insert(0, tokens[i])
        i -= 1
    if i > 1 and tokens[i][0].isalpha():
        name = tokens[i]
        i -= 1
    else:
        return None
    # 分离 array_range 与 init
    array_range = ""
    init = ""
    for p in right_parts:
        ps = p.rstrip(",;")
        if ps.startswith("["):
            array_range += (" " if array_range else "") + p
        else:
            init += (" " if init else "") + p
    # 中间 part → opt_type / opt_range
    middle = tokens[2:i + 1]
    opt_type = ""
    opt_range = ""
    for t in middle:
        if t in ("reg", "wire", "signed", "unsigned"):
            opt_type = t
        elif t.startswith("["):
            opt_range = t
    return [indent, first, opt_type, opt_range, name, array_range, init]


def _join_semantic(cols: list[str], widths: list[int]) -> str:
    parts = [cols[0]]
    for j in range(1, len(cols)):
        val = cols[j]
        if not val:
            parts.append(" " if 1 <= j <= 4 else "")
            continue
        if j >= 5:
            parts.append(" " + val)
        elif j < 4:
            parts.append(val + " " * (widths[j] - len(val) + 1))
        else:
            parts.append(val + " " * (widths[j] - len(val)))
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
