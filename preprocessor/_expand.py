"""Macro expansion — strip directives, expand `` `NAME `` references.

Pipeline: scan_directives() → expand_tokens() → Lexer
Both operate on pure text, no token dependency.

指令处理由 primitives/registry.py 的注册表分发，新增指令不修改本文件。
"""

import os
import re

from .primitives.registry import get_primitive
from .primitives.include import resolve_source_dir


def _get_expand_config() -> dict:
    """从 ConfigRegistry 获取展开器参数，未配置时返回默认值。"""
    from core.config_registry import config
    from core.config_map import PREPROCESSOR_EXPAND
    try:
        return dict(config.get(PREPROCESSOR_EXPAND))
    except (KeyError, RuntimeError):
        return {"max_iterations": 128}


def _get_include_config() -> dict:
    """从 ConfigRegistry 获取 include 配置，未配置时返回默认值。"""
    from core.config_registry import config
    from core.config_map import PREPROCESSOR_DIRECTIVES
    try:
        raw = dict(config.get(PREPROCESSOR_DIRECTIVES))
        return dict(raw.get("include", {}))
    except (KeyError, RuntimeError):
        return {"search_dirs": [], "silent": False}


def _load_config(rules_dir: str) -> tuple[str, set[str]]:
    """Load macro config → (prefix, directives_set)."""
    from ._config import load_macro_config

    cfg = load_macro_config()
    recognition = cfg.get("macro_recognition", {})
    prefix = recognition.get("prefix", "`")
    directives = set(cfg.get("directives", {}).values())
    return prefix, directives


def _build_macro_re(prefix: str) -> re.Pattern:
    return re.compile(rf"\{prefix}(\w+)")


# ============================================================
# 纯文本展开（新方案）
# ============================================================


def scan_directives(
    source: str,
    rules_dir: str,
    *,
    source_path: str | None = None,
    _include_stack: set[str] | None = None,
    search_dirs: list[str] | None = None,
) -> tuple[dict[str, str], list[str], str]:
    """扫描源文件中的宏指令，构建宏表并返回清洗后的源码。

    Returns: (macro_defs, directive_lines, clean_source)
        macro_defs:     name → fully-expanded body
        directive_lines: 原始指令文本（用于 render 后恢复）
        clean_source:    去掉指令行后的源码
    """
    prefix, directives = _load_config(rules_dir)
    _MACRO_RE = _build_macro_re(prefix)

    if _include_stack is None:
        _include_stack = set()

    # include 配置（从 ConfigRegistry 读）
    inc_config = _get_include_config()

    # 搜索路径：CLI 传入的 search_dirs 优先，合并配置中的 search_dirs
    cli_dirs = search_dirs or []
    cfg_dirs = inc_config.get("search_dirs", [])
    src_dir = resolve_source_dir(source_path, rules_dir)
    all_dirs = cli_dirs + cfg_dirs + [src_dir, rules_dir]

    # Handler 共享上下文
    ctx = {
        "macro_defs": {},
        "directive_lines": [],
        "_inject_lines": [],
        "_include_stack": _include_stack,
        "source_dir": src_dir,
        "inc_dirs": all_dirs,
        "rules_dir": rules_dir,
        "_include_config": inc_config,
    }

    lines = source.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(prefix):
            ctx["_inject_lines"].append(line)
            continue

        # 指令行
        ctx["directive_lines"].append(stripped)

        # 从指令行提取 directive 关键字
        # `define foo bar → "define"
        after_prefix = stripped[len(prefix):]
        space_pos = after_prefix.find(" ")
        directive_name = after_prefix[:space_pos] if space_pos > 0 else after_prefix

        handler = get_primitive(directive_name)
        if handler:
            handler(stripped, prefix, directive_name, ctx)

    macro_defs = ctx["macro_defs"]
    directive_lines = ctx["directive_lines"]
    clean_source = "\n".join(ctx["_inject_lines"])

    if not macro_defs:
        return {}, directive_lines, clean_source

    # ---- 宏体全展开（为 reverser 提供已展开的值）----
    expand_cfg = _get_expand_config()
    max_iter = expand_cfg.get("max_iterations", 128)
    for _ in range(max_iter):
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

    return macro_defs, directive_lines, clean_source


def _find_sync_word(line: str, macro_col: int, prev_line: str = "") -> tuple[str, int]:
    """向左找最近的非空白词作为同步词。

    优先在当前行找，找不到则尝试上一行末尾词。
    Returns: (sync_text, offset_from_sync_end_to_macro_start)
    """
    # 当前行向左找
    pos = macro_col - 1
    while pos >= 0 and line[pos] in ' \t':
        pos -= 1
    if pos >= 0:
        word_end = pos + 1
        while pos >= 0 and line[pos] not in ' \t':
            pos -= 1
        sync_text = line[pos + 1:word_end]
        offset = macro_col - word_end
        return sync_text, offset

    # 当前行没有 → 取上一行末尾非空白词
    if prev_line:
        pos = len(prev_line) - 1
        while pos >= 0 and prev_line[pos] in ' \t':
            pos -= 1
        if pos >= 0:
            word_end = pos + 1
            while pos >= 0 and prev_line[pos] not in ' \t':
                pos -= 1
            sync_text = prev_line[pos + 1:word_end]
            offset = macro_col + 1
            return sync_text, offset

    return "", macro_col


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
    _MACRO_RE = re.compile(rf"\{prefix}(\w+)")
    restoration_stack: list[dict] = []
    lines = source.split("\n")

    for line_no, line in enumerate(lines, 1):
        macro_matches: list[tuple[int, int, str, str]] = []
        for m in _MACRO_RE.finditer(line):
            name = m.group(1)
            body = macro_defs.get(name)
            if body is None:
                continue
            macro_col = m.start()
            macro_matches.append((macro_col, m.end(), body, name))

        if not macro_matches:
            continue

        prev_line = lines[line_no - 2] if line_no >= 2 else ""

        # 统计行内同步词出现次数，确定每个宏对应第几个同步词
        sync_counter: dict[str, int] = {}
        for macro_col, macro_end, body, name in sorted(macro_matches):
            sync_text, _ = _find_sync_word(line, macro_col, prev_line)
            sync_counter[sync_text] = sync_counter.get(sync_text, 0) + 1

        # 从右到左替换（避免位置偏移）
        parts = list(line)
        forward_entries: list[dict] = []
        for macro_col, macro_end, body, name in reversed(macro_matches):
            sync_text, offset = _find_sync_word(line, macro_col, prev_line)
            nth = sync_counter[sync_text]
            sync_counter[sync_text] = nth - 1  # 从右到左递减

            # 替换
            parts[macro_col:macro_end] = body

            # 记录（逆序 processing，但用头插保证正序）
            forward_entries.append({
                "macro": name,
                "body": body,
                "sync": sync_text,
                "sync_nth": nth,
                "offset": offset,
            })

        # 正序存入 restoration_stack（匹配渲染输出的出现顺序）
        restoration_stack.extend(reversed(forward_entries))

        lines[line_no - 1] = "".join(parts)

    return "\n".join(lines), restoration_stack
