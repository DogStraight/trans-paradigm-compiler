"""Macro expansion — strip directives, expand `` `NAME `` references.

Two modes:
  1. String-level (legacy):  preprocess() — expands in source text
  2. Token-level (preferred): scan_directives() + expand_tokens() — expands
     in Lexer-produced token stream.
"""

import re
from typing import Optional

from core.define import Token

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


def expand_tokens(
    tokens: list[Token],
    macro_defs: dict[str, str],
    lexer,
    prefix: str = "`",
) -> list[Token]:
    """在 Token 流中展开 macro.call  token。

    按行分组处理：对含 macro.call 的行，将宏体替换后重建文本并重新 tokenize。
    这样 Lexer 的 NumberFSM 能在完整行上下文中工作（如 8'b0 不会被宏切开）。

    文本重建规则：
    - 非宏 token 尾部加空格 → 保持 token 边界独立
    - 宏体直接插入，不加空格 → 自动与相邻 token 合并（如 8 贴着 'b0 → 8'b0）
    同时过滤 macro.define / macro.include 等指令 token。

    Returns (expanded_tokens, expansion_stack):
        expansion_stack — reverser 使用的上下文锚点列表，每项含：
            macro: 宏名
            body: 宏体文本
            ctx_before: [(type, content), ...]  宏展开前 N 个 token
            ctx_after:  [(type, content), ...]  宏展开后 N 个 token
    """
    CTX_WINDOW = 2

    result: list[Token] = []
    expansion_stack: list[dict] = []
    i = 0
    while i < len(tokens):
        # 收集一行（不含换行）
        line_start = i
        while i < len(tokens) and tokens[i].type != "newline":
            i += 1
        line_tokens = tokens[line_start:i]

        # 检查行内是否有 macro.call
        has_macro = any(t.type == "macro.call" for t in line_tokens)

        if has_macro:
            # ---- 记录展开上下文栈 ----
            for mi, t in enumerate(line_tokens):
                if t.type != "macro.call":
                    continue
                name = t.content[1:]
                body = macro_defs.get(name)
                if not body:
                    continue

                # 前文：向前取 CTX_WINDOW 个非宏、非换行 token
                ctx_before: list[tuple[str, str]] = []
                for j in range(mi - 1, -1, -1):
                    if len(ctx_before) >= CTX_WINDOW:
                        break
                    tj = line_tokens[j]
                    if not tj.type.startswith("macro.") and tj.type != "newline":
                        ctx_before.insert(0, (tj.type, tj.content))

                # 后文：向后取 CTX_WINDOW 个非宏、非换行 token
                ctx_after: list[tuple[str, str]] = []
                for j in range(mi + 1, len(line_tokens)):
                    if len(ctx_after) >= CTX_WINDOW:
                        break
                    tj = line_tokens[j]
                    if not tj.type.startswith("macro.") and tj.type != "newline":
                        ctx_after.append((tj.type, tj.content))

                expansion_stack.append({
                    "macro": name,
                    "body": body,
                    "ctx_before": ctx_before,
                    "ctx_after": ctx_after,
                })

            # ---- 重建行文本并重新 tokenize ----
            parts: list[str] = []
            for t in line_tokens:
                if t.type == "macro.call":
                    name = t.content[1:]
                    parts.append(macro_defs.get(name, t.content))
                elif not t.type.startswith("macro."):
                    parts.append(t.content + " ")
            line_text = "".join(parts)
            new_tokens = lexer.tokenize(line_text)
            result.extend(new_tokens)
        else:
            # 无宏的行：原样通过（过滤指令 token）
            for t in line_tokens:
                if not t.type.startswith("macro."):
                    result.append(t)

        # 保留换行 token
        if i < len(tokens) and tokens[i].type == "newline":
            result.append(tokens[i])
            i += 1

    return result, expansion_stack


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
