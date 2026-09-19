"""ifdef.py — 条件编译块内容缩进 pass

处理 ifdef/ifndef 块：指令行本身顶格（indent pass 已处理），但当 ifdef 块
紧跟单语句头（如 `if (X)` / `for (...)` 无 begin）时，块内内容是语句头的
单语句体，应继承悬挂缩进（+1 级）。elsif/else 各分支内容同样继承。

只改 ifdef 块内容行的行首空白，不碰 token（保证 token 完整性）。
"""

from __future__ import annotations

from ..boundary import LineContext
from ..style import line_indent_width

_IFDEF_DIRECTIVE = ("`ifdef", "`ifndef", "`elsif", "`else", "`endif")


def _prev_non_directive(
    contexts: list[LineContext], idx: int
) -> LineContext | None:
    """上溯到最近的非指令行（跨过 ifdef 家族指令行）；无 → None。"""
    k = idx - 1
    while k >= 0:
        cand = contexts[k]
        if not cand.text.lstrip().startswith(_IFDEF_DIRECTIVE):
            return cand
        k -= 1
    return None


def _reindent_block_body(
    result: list[str],
    contexts: list[LineContext],
    start: int,
    indent_width: int,
) -> None:
    """ifdef 块内内容行缩进 +1 级（用 ifdef/endif 配对界定块范围）。

    不能依赖 in_ifdef：外层还有 ifdef 时，块后内容仍 in_ifdef。
    只改行首空白，不碰 token（保证 token 完整性）。
    """
    k = start
    depth = 0
    while k < len(contexts):
        c = contexts[k]
        ctext = c.text.lstrip()
        if ctext.startswith(("`ifdef", "`ifndef")):
            depth += 1
        elif ctext.startswith("`endif"):
            if depth == 0:
                return  # 匹配到本 ifdef 的 endif
            depth -= 1
        elif not ctext.startswith(("`elsif", "`else")):
            ln = c.line_number - 1
            if 0 <= ln < len(result):
                stripped = result[ln].lstrip()
                if stripped:
                    level = line_indent_width(result[ln]) // indent_width + 1
                    result[ln] = " " * (level * indent_width) + stripped
        k += 1


def run_ifdef_pass(
    lines: list[str],
    contexts: list[LineContext],
    indent_width: int = 4,
) -> list[str]:
    result = list(lines)
    for idx, ctx in enumerate(contexts):
        if not ctx.text.lstrip().startswith(("`ifdef", "`ifndef")):
            continue
        # 悬挂上下文：ifdef 指令行之前（跨过其他指令行）最近的非指令行是否是
        # 无 begin 的单语句头（if/for/else）。是 → 该 ifdef 块内容是语句头的
        # 单语句体，继承悬挂（+1 级）
        prev = _prev_non_directive(contexts, idx)
        if prev is None or not prev.single_stmt_header:
            continue
        _reindent_block_body(result, contexts, idx + 1, indent_width)
    return result
