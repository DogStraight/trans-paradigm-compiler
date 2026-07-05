"""Macro reversal — restore `` `NAME `` from expanded values.

Two strategies:
  1. Token sequence matching (preferred) — uses Lexer to tokenize both
     macro bodies and rendered output, then matches by token type + content.
     Handles whitespace differences and provides safety thresholds.
  2. String-based matching (fallback) — original heuristic approach
     (column proximity scoring + global find-and-replace).
"""

import logging
from typing import Optional

from core.define import Token

# ============================================================
# 安全阈值
# ============================================================
MIN_MATCH_TOKENS = 3  # 匹配窗口永不缩到 3 Token 以下
_SENTINEL = "@@PYV@@"


# ============================================================
# Fallback: 字符串匹配（原有逻辑保留不动）
# ============================================================

_COL_WEIGHT = 1000


def _is_word_boundary(line: str, pos: int) -> bool:
    if pos <= 0 or pos >= len(line):
        return True
    return not (line[pos - 1].isalnum() or line[pos - 1] == "_")


def _find_literal_sites(
    source: str, macro_defs: dict[str, str], prefix: str
) -> list[tuple[int, int, str]]:
    sites: list[tuple[int, int, str]] = []
    values = set(macro_defs.values())
    if not values:
        return sites
    for line_no, line in enumerate(source.split("\n"), 1):
        if line.lstrip().startswith(prefix):
            continue
        for value in values:
            search_from = 0
            while True:
                col = line.find(value, search_from)
                if col == -1:
                    break
                if col > 0 and line[col - 1] == prefix:
                    search_from = col + len(value)
                    continue
                after = col + len(value)
                if _is_word_boundary(line, col) and _is_word_boundary(line, after):
                    sites.append((line_no, col + 1, value))
                search_from = col + len(value)
    return sites


def _reverse_by_string(
    rendered: str,
    original_source: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
    window: int = 3,
) -> str:
    """Original string-based heuristic reversal."""
    literal_sites = _find_literal_sites(original_source, macro_defs, prefix)
    if not literal_sites:
        return _reverse_macros_simple(rendered, macro_defs, prefix, define_keyword)

    rendered_lines = rendered.split("\n")
    placeholders: dict[str, str] = {}
    placements: list[tuple[int, int, str, str]] = []

    for idx, (src_line, src_col, value) in enumerate(literal_sites):
        ph = f"{_SENTINEL}{idx}{_SENTINEL}"
        placeholders[ph] = value
        best_line = -1
        best_col = -1
        best_dist = float("inf")
        for offset in range(-window, window + 1):
            line_idx = src_line - 1 + offset
            if line_idx < 0 or line_idx >= len(rendered_lines):
                continue
            line = rendered_lines[line_idx]
            search_from = 0
            while True:
                pos = line.find(value, search_from)
                if pos == -1:
                    break
                after = pos + len(value)
                if _is_word_boundary(line, pos) and _is_word_boundary(line, after):
                    dist = abs(offset) * _COL_WEIGHT + abs(pos + 1 - src_col)
                    if dist < best_dist:
                        best_dist = dist
                        best_line = line_idx
                        best_col = pos
                search_from = pos + len(value)
        if best_line >= 0:
            placements.append((best_line, best_col, ph, value))

    placements.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for line_idx, col, ph, value in placements:
        line = rendered_lines[line_idx]
        rendered_lines[line_idx] = line[:col] + ph + line[col + len(value) :]

    protected = "\n".join(rendered_lines)
    result = _reverse_macros_simple(protected, macro_defs, prefix, define_keyword)
    for ph, value in placeholders.items():
        result = result.replace(ph, value)
    return result


def _reverse_macros_simple(
    output: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
) -> str:
    """Simple global find-and-replace by longest-value-first."""
    items = sorted(macro_defs.items(), key=lambda x: len(x[1]), reverse=True)
    lines = output.split("\n")
    for name, value in items:
        def_line_prefix = f"{prefix}{define_keyword} {name}"
        for i, line in enumerate(lines):
            if line.lstrip().startswith(def_line_prefix):
                continue
            lines[i] = line.replace(value, f"{prefix}{name}")
    return "\n".join(lines)


# ============================================================
# Token 序列匹配（新策略）
# ============================================================


def _compute_line_offsets(text: str) -> list[int]:
    """每行（0-based）在原文中的起始字符偏移。"""
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _token_start(tok: Token, line_offsets: list[int]) -> int:
    return line_offsets[tok.line - 1] + tok.column


def _token_end(tok: Token, line_offsets: list[int]) -> int:
    return _token_start(tok, line_offsets) + len(tok.content)


def _is_skippable(tok: Token) -> bool:
    return tok.type.startswith("space.") or tok.type == "comment"


def _try_match_sequence(
    rtokens: list[Token],
    start_idx: int,
    macro_seq: list[tuple[str, str]],
) -> Optional[int]:
    """尝试从 start_idx 匹配 macro_seq，返回消耗的 token 数（含跳过）。"""
    mi = 0
    ri = start_idx
    while mi < len(macro_seq) and ri < len(rtokens):
        rt = rtokens[ri]
        if _is_skippable(rt):
            ri += 1
            continue
        if rt.type == macro_seq[mi][0] and rt.content == macro_seq[mi][1]:
            mi += 1
            ri += 1
        else:
            return None
    if mi == len(macro_seq):
        return ri
    return None


def _check_context(
    rtokens: list[Token],
    match_start: int,
    match_end: int,
    ctx_before: list[tuple[str, str]],
    ctx_after: list[tuple[str, str]],
) -> bool:
    """检查匹配位置上下文的 token 是否与展开栈记录一致。"""
    # 检查前文
    ci = len(ctx_before) - 1
    ri = match_start - 1
    while ci >= 0 and ri >= 0:
        if _is_skippable(rtokens[ri]):
            ri -= 1
            continue
        if (rtokens[ri].type, rtokens[ri].content) != ctx_before[ci]:
            return False
        ci -= 1
        ri -= 1
    if ci >= 0:
        return False  # 前文 token 不够

    # 检查后文
    ci = 0
    ri = match_end
    while ci < len(ctx_after) and ri < len(rtokens):
        if _is_skippable(rtokens[ri]):
            ri += 1
            continue
        if (rtokens[ri].type, rtokens[ri].content) != ctx_after[ci]:
            return False
        ci += 1
        ri += 1
    if ci < len(ctx_after):
        return False  # 后文 token 不够

    return True


def _reverse_by_stack(
    rendered: str,
    macro_defs: dict[str, str],
    prefix: str,
    lexer,
    expansion_stack: list[dict],
) -> str:
    """基于展开栈上下文锚点的精确宏还原。

    每个展开记录携带宏展开时的前/后文 token（ctx_before/ctx_after）。
    在渲染结果中找到宏体位置后，验证上下文是否匹配，消除歧义。
    """
    rtokens = lexer.tokenize(rendered)
    line_offsets = _compute_line_offsets(rendered)
    replacements: list[tuple[int, int, str]] = []
    replaced = [False] * len(rtokens)
    reversed_names: set[str] = set()

    for entry in expansion_stack:
        name = entry["macro"]
        body = entry["body"]
        ctx_before = entry["ctx_before"]
        ctx_after = entry["ctx_after"]

        # Tokenize 宏体
        body_tokens = lexer.tokenize(body)
        body_seq = [(t.type, t.content) for t in body_tokens if not _is_skippable(t)]
        if not body_seq:
            continue

        # 在渲染结果中查找匹配
        candidate_spans: list[tuple[int, int]] = []
        ri = 0
        while ri < len(rtokens):
            if replaced[ri] or _is_skippable(rtokens[ri]):
                ri += 1
                continue
            match_end = _try_match_sequence(rtokens, ri, body_seq)
            if match_end is not None:
                if _check_context(rtokens, ri, match_end, ctx_before, ctx_after):
                    candidate_spans.append((ri, match_end))
                ri = match_end
            else:
                ri += 1

        if len(candidate_spans) == 1:
            ri_start, ri_end = candidate_spans[0]
            c_start = _token_start(rtokens[ri_start], line_offsets)
            c_end = _token_end(rtokens[ri_end - 1], line_offsets)
            replacements.append((c_start, c_end, f"{prefix}{name}"))
            reversed_names.add(name)
            for i in range(ri_start, ri_end):
                replaced[i] = True
        elif len(candidate_spans) > 1:
            logging.warning(
                f"macro '{name}' ambiguous: {len(candidate_spans)} context-matched "
                f"candidates, falling back to string match"
            )
        # 0 candidates: skip

    # 执行替换
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = rendered
    for c_start, c_end, new_text in replacements:
        result = result[:c_start] + new_text + result[c_end:]

    # 未匹配的宏用字符串替换兜底
    remaining = {
        name: body
        for name, body in macro_defs.items()
        if name not in reversed_names
    }
    if remaining:
        result = _reverse_macros_simple(result, remaining, prefix, "define")

    return result


def _reverse_by_tokens(
    rendered: str,
    macro_defs: dict[str, str],
    prefix: str,
    define_keyword: str,
    lexer,
    expansion_stack: Optional[list[dict]] = None,
) -> str:
    """Token 序列匹配的宏还原。"""

    # 如果有展开栈，优先使用上下文锚点匹配
    if expansion_stack:
        return _reverse_by_stack(
            rendered, macro_defs, prefix, lexer, expansion_stack
        )

    # ---- 原有 Token 序列匹配逻辑（展开栈不存在时 fallback）----

    # ---- 1. Tokenize 宏体 ----
    macro_seqs: dict[str, list[tuple[str, str]]] = {}
    for name, body in macro_defs.items():
        raw = lexer.tokenize(body)
        seq = [(t.type, t.content) for t in raw if not _is_skippable(t)]
        if seq:
            macro_seqs[name] = seq

    if not macro_seqs:
        return rendered

    # ---- 2. Tokenize 渲染输出 ----
    rtokens = lexer.tokenize(rendered)
    line_offsets = _compute_line_offsets(rendered)

    # ---- 3. 构建替换计划 ----
    sorted_macros = sorted(
        macro_seqs.items(), key=lambda kv: len(kv[1]), reverse=True
    )
    replacements: list[tuple[int, int, str]] = []
    replaced = [False] * len(rtokens)
    reversed_names: set[str] = set()

    for name, mseq in sorted_macros:
        candidate_spans: list[tuple[int, int]] = []
        ri = 0
        while ri < len(rtokens):
            if replaced[ri] or _is_skippable(rtokens[ri]):
                ri += 1
                continue
            match_end = _try_match_sequence(rtokens, ri, mseq)
            if match_end is not None:
                candidate_spans.append((ri, match_end))
                ri = match_end
            else:
                ri += 1

        if not candidate_spans:
            continue

        # ---- 消歧 ----
        if len(candidate_spans) == 1:
            span = candidate_spans[0]
        elif len(mseq) > MIN_MATCH_TOKENS:
            resolved = False
            resolved_span = None
            for window in range(len(mseq) - 1, MIN_MATCH_TOKENS - 1, -1):
                sub_seq = mseq[:window]
                sub_spans: list[tuple[int, int]] = []
                for ri_start, _ in candidate_spans:
                    me = _try_match_sequence(rtokens, ri_start, sub_seq)
                    if me is not None:
                        sub_spans.append((ri_start, me))
                if len(sub_spans) == 1:
                    resolved_span = sub_spans[0]
                    resolved = True
                    break
            if resolved:
                span = resolved_span
            else:
                logging.warning(
                    f"macro '{name}' ambiguous: {len(candidate_spans)} candidates "
                    f"even at minimum window size, "
                    f"falling back to string match"
                )
                continue
        else:
            logging.warning(
                f"macro '{name}' ambiguous: {len(candidate_spans)} candidates, "
                f"falling back to string match"
            )
            continue

        ri_start, ri_end = span
        c_start = _token_start(rtokens[ri_start], line_offsets)
        c_end = _token_end(rtokens[ri_end - 1], line_offsets)
        replacements.append((c_start, c_end, f"{prefix}{name}"))
        reversed_names.add(name)
        for i in range(ri_start, ri_end):
            replaced[i] = True

    # ---- 4. 从后往前执行 Token 替换 ----
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = rendered
    for c_start, c_end, new_text in replacements:
        result = result[:c_start] + new_text + result[c_end:]

    # ---- 5. 未通过 Token 匹配的宏用字符串替换兜底 ----
    remaining = {
        name: body
        for name, body in macro_defs.items()
        if name not in reversed_names
    }
    if remaining:
        result = _reverse_macros_simple(
            result, remaining, prefix, define_keyword
        )

    return result


# ============================================================
# 公开接口
# ============================================================


def reverse_macros(
    output: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
) -> str:
    """Restore macro references by global find-and-replace (string match).

    Retained for backward compatibility. Prefer `protect_and_reverse`
    with a `lexer` argument for better accuracy.
    """
    return _reverse_macros_simple(output, macro_defs, prefix, define_keyword)


def protect_and_reverse(
    rendered: str,
    original_source: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
    window: int = 3,
    lexer=None,
    expansion_stack: Optional[list[dict]] = None,
) -> str:
    """Reverse macro expansion in rendered output.

    If `expansion_stack` is provided, uses context-anchored matching (best).
    Elif `lexer` is provided, uses Token sequence matching.
    Otherwise falls back to string-based heuristic.
    """
    if expansion_stack and lexer is not None:
        return _reverse_by_stack(
            rendered, macro_defs, prefix, lexer, expansion_stack
        )
    if lexer is not None:
        return _reverse_by_tokens(
            rendered, macro_defs, prefix, define_keyword, lexer
        )
    return _reverse_by_string(
        rendered, original_source, macro_defs, prefix, define_keyword, window
    )
