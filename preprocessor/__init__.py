"""Preprocessor — TOML-driven Verilog macro expansion.

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse

Expand:  collect `define → macro table → iterative `MACRO → value
Reverse: global find-replace value → `MACRO, longest first, skip define lines
"""

import re
import tomllib
from pathlib import Path
from core.define import FileManager

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

_MAX_ITERATIONS = 128       # safety limit against circular `define
_COL_WEIGHT = 1000          # line-offset weight in column-proximity scoring
_SENTINEL = "@@PYV@@"        # placeholder marker — cannot appear in any Verilog token

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def load_macro_config(rules_dir: str) -> dict:
    """Load base/_macro.toml configuration."""
    base = Path(FileManager.get_full_path(rules_dir)) / "base" / "_macro.toml"
    if not base.exists():
        return {}
    with open(base, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# expand
# ---------------------------------------------------------------------------


def preprocess(source: str, rules_dir: str) -> tuple[str, dict[str, str]]:
    """Expand `define macros → (expanded_source, macro_defs).

    macro_defs maps name → fully-expanded body.
    """
    config = load_macro_config(rules_dir)
    prefix = config.get("macro_call", {}).get("prefix", "`")
    directives = set(config.get("directives", {}).values())

    macro_defs: dict[str, str] = {}
    _MACRO_RE = re.compile(rf"\{prefix}(\w+)")
    _DEFINE_RE = re.compile(
        rf"\{prefix}({'|'.join(directives)})\s+(\w+)\s+(.*?)\s*$",
        re.MULTILINE,
    )

    for m in _DEFINE_RE.finditer(source):
        name, body = m.group(2), m.group(3)
        macro_defs[name] = body.strip()

    if not macro_defs:
        return source, {}

    # ---- iterative expansion of source text ----
    result = source
    for _ in range(_MAX_ITERATIONS):
        changed = False

        def _expand(m: re.Match) -> str:
            nonlocal changed
            name = m.group(1)
            if name in directives:
                return m.group(0)
            if name in macro_defs:
                changed = True
                return macro_defs[name]
            return m.group(0)

        result = _MACRO_RE.sub(_expand, result)
        if not changed:
            break

    # ---- fully expand nested macros in bodies (for reverse ordering) ----
    for _ in range(_MAX_ITERATIONS):
        changed = False
        for name, body in macro_defs.items():
            new_body = _MACRO_RE.sub(
                lambda m: macro_defs.get(m.group(1), m.group(0)), body
            )
            if new_body != body:
                changed = True
                macro_defs[name] = new_body
        if not changed:
            break

    return result, macro_defs


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _is_word_boundary(line: str, pos: int) -> bool:
    """Check if line[pos] starts a new word (not mid-identifier)."""
    if pos <= 0 or pos >= len(line):
        return True
    return not (line[pos - 1].isalnum() or line[pos - 1] == "_")


# ---------------------------------------------------------------------------
# literal protection (anti-pollution)
# ---------------------------------------------------------------------------


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
                # skip `` `NAME `` calls
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
    # ---- step 1 ----
    literal_sites = _find_literal_sites(original_source, macro_defs, prefix)
    if not literal_sites:
        return reverse_macros(rendered, macro_defs, prefix, define_keyword)

    # ---- step 2+3: column-aware placement ----
    rendered_lines = rendered.split("\n")
    placeholders: dict[str, str] = {}  # ph → original value

    # group by rendered-line-index to process right-to-left within each line
    placements: list[tuple[int, int, str, str]] = []  # (line_idx, col, ph, value)

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
            # find ALL occurrences of value on this line
            search_from = 0
            while True:
                pos = line.find(value, search_from)
                if pos == -1:
                    break
                after = pos + len(value)
                if _is_word_boundary(line, pos) and _is_word_boundary(line, after):
                    # column-weighted distance
                    dist = abs(offset) * _COL_WEIGHT + abs(pos + 1 - src_col)
                    if dist < best_dist:
                        best_dist = dist
                        best_line = line_idx
                        best_col = pos
                search_from = pos + len(value)

        if best_line >= 0:
            placements.append((best_line, best_col, ph, value))

    # apply right-to-left within each line so earlier columns stay valid
    placements.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for line_idx, col, ph, value in placements:
        line = rendered_lines[line_idx]
        rendered_lines[line_idx] = line[:col] + ph + line[col + len(value) :]

    protected = "\n".join(rendered_lines)

    # ---- step 4: macro reversal ----
    result = reverse_macros(protected, macro_defs, prefix, define_keyword)

    # ---- step 5: restore placeholders ----
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
