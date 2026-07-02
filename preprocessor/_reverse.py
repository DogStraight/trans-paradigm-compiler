"""Macro reversal — restore `` `NAME `` from values, protect literals."""

import re

_COL_WEIGHT = 1000     # line-offset weight in column-proximity scoring
_SENTINEL = "@@PYV@@"  # placeholder marker


def _is_word_boundary(line: str, pos: int) -> bool:
    """Check if line[pos] starts a new word (not mid-identifier)."""
    if pos <= 0 or pos >= len(line):
        return True
    return not (line[pos - 1].isalnum() or line[pos - 1] == "_")


def _find_literal_sites(
    source: str,
    macro_defs: dict[str, str],
    prefix: str,
) -> list[tuple[int, int, str]]:
    """Find positions in *original source* where a macro VALUE appears
    as a literal (not a `` `NAME `` call and not inside a define line).

    Returns list of (line_no, col, value) — 1-based line & column.
    """
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


def protect_and_reverse(
    rendered: str,
    original_source: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
    window: int = 3,
) -> str:
    """Protect literal values, reverse macros, then restore literals.

    1. Scan *original source* for literals matching macro values.
    2. In the *rendered output*, locate each literal by line ± window
       and column proximity (not first-find).
    3. Replace with unique placeholders (`` __PH_N__ ``).
    4. Run macro reversal.
    5. Restore placeholders → original literal values.
    """
    literal_sites = _find_literal_sites(original_source, macro_defs, prefix)
    if not literal_sites:
        return reverse_macros(rendered, macro_defs, prefix, define_keyword)

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

    result = reverse_macros(protected, macro_defs, prefix, define_keyword)

    for ph, value in placeholders.items():
        result = result.replace(ph, value)

    return result


def reverse_macros(
    output: str,
    macro_defs: dict[str, str],
    prefix: str = "`",
    define_keyword: str = "define",
) -> str:
    """Restore macro references by global find-and-replace.

    Processed longest-value-first so outer macros are reversed before
    inner ones.  Each macro's own `` `define `` line is skipped.
    """
    items = [(name, value) for name, value in macro_defs.items()]
    items.sort(key=lambda x: len(x[1]), reverse=True)

    lines = output.split("\n")

    for name, value in items:
        defline_prefix = f"{prefix}{define_keyword} {name}"
        for i, line in enumerate(lines):
            if line.lstrip().startswith(defline_prefix):
                continue
            lines[i] = line.replace(value, f"{prefix}{name}")

    return "\n".join(lines)
