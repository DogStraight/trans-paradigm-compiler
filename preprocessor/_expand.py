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

    将每个 macro.call("`NAME") 替换为宏体经 Lexer tokenize 后的 Token 序列。
    同时过滤 macro.define / macro.include 等指令 token。
    保留非宏 Token 不变。
    """
    result: list[Token] = []
    for tok in tokens:
        if tok.type.startswith("macro."):
            if tok.type == "macro.call":
                name = tok.content[1:]  # 去掉 ` 前缀
                body = macro_defs.get(name)
                if body is not None:
                    body_tokens = lexer.tokenize(body)
                    result.extend(body_tokens)
                else:
                    result.append(tok)
            # macro.define / macro.include 等指令 token → 丢弃
            continue
        result.append(tok)
    return result


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
