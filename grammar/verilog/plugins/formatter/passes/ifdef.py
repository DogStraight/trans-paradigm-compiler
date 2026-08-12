"""ifdef.py — 条件编译块内容缩进 pass

处理 ifdef/ifndef 块：指令行本身顶格（indent pass 已处理），但当 ifdef 块
紧跟单语句头（如 `if (X)` / `for (...)` 无 begin）时，块内内容是语句头的
单语句体，应继承悬挂缩进（+1 级）。elsif/else 各分支内容同样继承。

只改 ifdef 块内容行的行首空白，不碰 token（保证 token 完整性）。
"""

from __future__ import annotations

from ..boundary import LineContext

_IFDEF_DIRECTIVE = ("`ifdef", "`ifndef", "`elsif", "`else", "`endif")


def _indent_level(line: str, width: int) -> int:
    """行首缩进换算为级数（tab=4 空格）。"""
    n = 0
    for c in line:
        if c == "\t":
            n += 4
        elif c == " ":
            n += 1
        else:
            break
    return n // width


def run_ifdef_pass(
    lines: list[str],
    contexts: list[LineContext],
    indent_width: int = 4,
) -> list[str]:
    result = list(lines)
    for idx, ctx in enumerate(contexts):
        text = ctx.text.lstrip()
        if not text.startswith(("`ifdef", "`ifndef")):
            continue
        # 悬挂上下文：ifdef 指令行之前（跨过其他指令行）最近的非指令行是否是
        # 无 begin 的单语句头（if/for/else）。是 → 该 ifdef 块内容是语句头的
        # 单语句体，继承悬挂（+1 级）
        prev = None
        _k = idx - 1
        while _k >= 0:
            cand = contexts[_k]
            if cand.text.lstrip().startswith(_IFDEF_DIRECTIVE):
                _k -= 1
                continue
            prev = cand
            break
        if prev is None or not prev.single_stmt_header:
            continue
        # ifdef 块内所有内容行（非指令行）→ +1 级。用 ifdef/endif 配对界定块
        # 范围（不能依赖 in_ifdef：外层还有 ifdef 时，块后内容仍 in_ifdef）
        _k = idx + 1
        _depth = 0
        while _k < len(contexts):
            c = contexts[_k]
            ctext = c.text.lstrip()
            if ctext.startswith(("`ifdef", "`ifndef")):
                _depth += 1
            elif ctext.startswith("`endif"):
                if _depth == 0:
                    break  # 匹配到本 ifdef 的 endif
                _depth -= 1
            elif not ctext.startswith(("`elsif", "`else")):
                ln = c.line_number - 1
                if 0 <= ln < len(result):
                    stripped = result[ln].lstrip()
                    if stripped:
                        level = _indent_level(result[ln], indent_width) + 1
                        result[ln] = " " * (level * indent_width) + stripped
            _k += 1
    return result
