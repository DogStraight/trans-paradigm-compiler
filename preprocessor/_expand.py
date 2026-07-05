"""Macro expansion — strip directives, expand `` `NAME `` references.

Two modes:
  1. String-level (legacy):  preprocess() — expands in source text
  2. Pure-text (preferred): scan_directives() + expand_tokens() — expands
     `` `NAME `` in source text before lexer.
"""

import re
_MAX_ITERATIONS = 128  # safety limit against circular `define


def _load_config(rules_dir: str) -> tuple[str, set[str]]:
    """Load macro config → (prefix, directives_set)."""
    from ._config import load_macro_config

    cfg = load_macro_config(rules_dir)
    prefix = cfg.get("macro_call", {}).get("prefix", "`")
    directives = set(cfg.get("directives", {}).values())
    return prefix, directives


def _build_macro_re(prefix: str) -> re.Pattern:
    return re.compile(rf"\{prefix}(\w+)")


# ============================================================
# Token 级展开（新方案）
# ============================================================


def scan_directives(
    source: str, rules_dir: str
) -> tuple[dict[str, str], list[str], str]:
    """扫描源文件中的宏指令，构建宏表并返回清洗后的源码。

    Returns: (macro_defs, directive_lines, clean_source)
        macro_defs:     name → fully-expanded body
        directive_lines: 原始指令文本（用于 render 后恢复）
        clean_source:    去掉指令行后的源码
    """
    prefix, directives = _load_config(rules_dir)
    _MACRO_RE = _build_macro_re(prefix)

    macro_defs: dict[str, str] = {}
    lines = source.split("\n")
    directive_lines: list[str] = []
    clean_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            # 指令行
            directive_lines.append(stripped)
            # 解析 `define
            if stripped.startswith(f"{prefix}define "):
                arg = stripped[len(prefix) + len("define "):]
                name_end = arg.find(" ")
                if name_end > 0:
                    def_name = arg[:name_end]
                    def_body = arg[name_end:].strip()
                    macro_defs[def_name] = def_body
                else:
                    macro_defs[arg] = ""
            elif stripped.startswith(f"{prefix}undef "):
                arg = stripped[len(prefix) + len("undef "):].strip()
                macro_defs.pop(arg, None)
            # include, timescale 等非 define/undef 指令：仅保留 line
        else:
            clean_lines.append(line)

    if not macro_defs:
        return {}, directive_lines, "\n".join(clean_lines)

    # ---- 宏体全展开（为 reverser 提供已展开的值）----
    for _ in range(_MAX_ITERATIONS):
        changed = False
        for name, body in list(macro_defs.items()):
            new_body = _MACRO_RE.sub(
                lambda m: macro_defs.get(m.group(1), m.group(0)), body
            )
            if new_body != body:
                changed = True
                macro_defs[name] = new_body
        if not changed:
            break

    return macro_defs, directive_lines, "\n".join(clean_lines)


def _find_sync_word(line: str, macro_col: int) -> tuple[str, int]:
    """向左找最近的非空白词作为同步词。

    Returns: (sync_text, offset_from_sync_end_to_macro_start)
    """
    # 跳过空白
    pos = macro_col - 1
    while pos >= 0 and line[pos] in ' \t':
        pos -= 1
    if pos < 0:
        return "", macro_col

    # 找到这个词的开头
    word_end = pos + 1
    while pos >= 0 and line[pos] not in ' \t':
        pos -= 1
    sync_text = line[pos + 1:word_end]
    offset = macro_col - word_end
    return sync_text, offset


def expand_tokens(
    source: str,
    macro_defs: dict[str, str],
    *,
    prefix: str = "`",
) -> tuple[str, list[dict]]:
    """在源码文本中展开宏调用（纯文本层）。

    用正则搜索 `NAME，向左扫同步词，记录位置后替换宏体。
    不再依赖 Token 流或 Lexer。

    Returns: (expanded_source, restoration_stack)
        restoration_stack — 逆序处理用的还原记录列表，每项含：
            macro, body, sync_text, offset
    """
    import re
    _MACRO_RE = re.compile(rf"\{prefix}(\w+)")
    restoration_stack: list[dict] = []
    lines = source.split("\n")

    for line_no, line in enumerate(lines, 1):
        # 在当前行中从右到左找宏调用，避免替换后偏移变化
        macro_matches: list[tuple[int, int, str, str]] = []
        for m in _MACRO_RE.finditer(line):
            name = m.group(1)
            body = macro_defs.get(name)
            if body is None:
                continue
            macro_col = m.start()  # 0-based column in the line
            macro_matches.append((macro_col, m.end(), body, name))

        if not macro_matches:
            continue

        # 统计行内同步词出现次数，确定每个宏对应第几个同步词
        sync_counter: dict[str, int] = {}
        # 按列号正序处理以计数
        for macro_col, macro_end, body, name in sorted(macro_matches):
            sync_text, _ = _find_sync_word(line, macro_col)
            sync_counter[sync_text] = sync_counter.get(sync_text, 0) + 1

        # 从右到左替换
        parts = list(line)
        for macro_col, macro_end, body, name in reversed(macro_matches):
            sync_text, offset = _find_sync_word(line, macro_col)
            nth = sync_counter[sync_text]
            sync_counter[sync_text] = nth - 1  # 从右到左递减

            # 替换
            parts[macro_col:macro_end] = body

            # 记录
            restoration_stack.append({
                "macro": name,
                "body": body,
                "sync": sync_text,
                "sync_nth": nth,
                "offset": offset,
            })

        lines[line_no - 1] = "".join(parts)

    return "\n".join(lines), restoration_stack


# ============================================================
# 字符串级展开（旧方案，保留向后兼容）
# ============================================================


def preprocess(source: str, rules_dir: str) -> tuple[str, dict[str, str], list[str]]:
    """Expand `define macros → (expanded_source, macro_defs, directive_lines).

    macro_defs maps name → fully-expanded body.
    directive_lines preserves original directive texts (stripped from output).

    Legacy string-level expansion. Prefer scan_directives() + expand_tokens()
    for new code.
    """
    prefix, directives = _load_config(rules_dir)
    _MACRO_RE = _build_macro_re(prefix)

    macro_defs, directive_lines, stripped_source = scan_directives(source, rules_dir)

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

    return result, macro_defs, directive_lines
