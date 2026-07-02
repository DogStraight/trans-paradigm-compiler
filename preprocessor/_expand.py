"""Macro expansion — strip directives, expand `` `NAME `` references."""

import re

_MAX_ITERATIONS = 128  # safety limit against circular `define


def preprocess(source: str, rules_dir: str) -> tuple[str, dict[str, str], list[str]]:
    """Expand `define macros → (expanded_source, macro_defs, directive_lines).

    macro_defs maps name → fully-expanded body.
    directive_lines preserves original directive texts (stripped from output).
    """
    from ._config import load_macro_config

    config = load_macro_config(rules_dir)
    prefix = config.get("macro_call", {}).get("prefix", "`")
    directives = set(config.get("directives", {}).values())

    macro_defs: dict[str, str] = {}
    _MACRO_RE = re.compile(rf"\{prefix}(\w+)")
    _DIRECTIVE_RE = re.compile(
        rf"\{prefix}(\w+)\b\s*(.*?)\s*$",
        re.MULTILINE,
    )

    # Phase 1: scan all directives, strip from source, record for reversal
    lines = source.split("\n")
    directive_lines: list[str] = []
    stripped_lines: list[str] = []

    for line in lines:
        for m in _DIRECTIVE_RE.finditer(line):
            directive_name = m.group(1)
            if directive_name not in directives:
                continue
            arg = m.group(2).strip()
            raw_directive = m.group(0).strip()

            if directive_name == "define":
                name_end = arg.find(" ")
                if name_end > 0:
                    def_name = arg[:name_end]
                    def_body = arg[name_end:].strip()
                    macro_defs[def_name] = def_body
                else:
                    macro_defs[arg] = ""
                directive_lines.append(raw_directive)

            elif directive_name == "undef":
                macro_defs.pop(arg, None)
                directive_lines.append(raw_directive)

            else:
                # include, timescale, ifdef, etc. — preserve for reversal
                directive_lines.append(raw_directive)

            line = ""
            break

        stripped_lines.append(line)

    stripped_source = "\n".join(stripped_lines)

    if not macro_defs:
        return stripped_source, {}, directive_lines

    # ---- iterative expansion of stripped source ----
    result = stripped_source
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

    return result, macro_defs, directive_lines
