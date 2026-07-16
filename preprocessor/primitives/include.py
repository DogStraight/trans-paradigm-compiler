"""include — `include "file" / <file> 指令处理器

支持 "..." 和 <...> 两种格式，含递归展开和循环检测。
"""

import os
import re
from .registry import register

# ── include 路径匹配 ──────────────────────────────

_INCLUDE_RE = re.compile(r'`include\s+"([^"]+)"')
_INCLUDE_ANGLE_RE = re.compile(r"`include\s+<([^>]+)>")


def resolve_source_dir(source_path: str | None, rules_dir: str) -> str:
    """返回源文件所在目录，用于相对路径 include 解析。"""
    if source_path and os.path.isfile(source_path):
        return os.path.dirname(os.path.abspath(source_path))
    return os.path.abspath(rules_dir)


def _resolve_path(
    raw_path: str, base_dir: str, search_dirs: list[str], is_angle: bool = False
) -> str | None:
    """解析 include 文件路径。

    "..." 格式：先相对当前目录，再按 search_dirs 搜索。
    <...> 格式：仅按 search_dirs 搜索（系统路径风格）。
    """
    if not is_angle:
        candidate = os.path.join(base_dir, raw_path)
        if os.path.isfile(candidate):
            return os.path.normpath(candidate)
    for d in search_dirs:
        candidate = os.path.join(d, raw_path)
        if os.path.isfile(candidate):
            return os.path.normpath(candidate)
    return None


@register("include")
def handle_include(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `include，支持 "..." 和 <...>。"""
    m = _INCLUDE_RE.match(stripped)
    is_angle = False
    if not m:
        m = _INCLUDE_ANGLE_RE.match(stripped)
        is_angle = True
    if not m:
        return

    inc_path = _resolve_path(
        m.group(1), ctx["source_dir"], ctx["inc_dirs"], is_angle=is_angle
    )
    if inc_path is None:
        silent = ctx.get("_include_config", {}).get("silent", False)
        if not silent:
            print(f"⚠️ [preprocessor] include 文件未找到: {m.group(1)}")
        return

    norm = os.path.normcase(inc_path)
    if norm in ctx["_include_stack"]:
        print(f"⚠️ [preprocessor] 循环 include 检测: {inc_path}，跳过")
        return

    ctx["_include_stack"].add(norm)
    try:
        with open(inc_path, encoding="utf-8") as f:
            inc_source = f.read()
        from .._expand import scan_directives

        inc_macros, inc_dirs_raw, inc_clean = scan_directives(
            inc_source,
            ctx["rules_dir"],
            source_path=inc_path,
            _include_stack=ctx["_include_stack"],
            search_dirs=ctx["inc_dirs"],
        )
        ctx["macro_defs"].update(inc_macros)
        ctx["directive_lines"].extend(inc_dirs_raw)
        ctx["_inject_lines"].extend(inc_clean.split("\n"))
    finally:
        ctx["_include_stack"].discard(norm)
