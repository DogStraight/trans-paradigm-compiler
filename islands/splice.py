"""splice.py — 编辑集应用与缩进基线回填。

编辑集是 `(start, end, replacement)` 字符区间列表；从右向左应用避免偏移串位。
缩进回填：岛文本从 token 起点截取（首行无前导空白），渲染结果从列 0 起；按插入位置
所在行的原始缩进整体前缀，保持与周围 water 的视觉连续（调研：clang-format/Black 的
局部处理边界效应都靠"扩展/重定基线"消化）。

Doc: islands/README.md
"""

from __future__ import annotations


def reindent(text: str, indent: str) -> str:
    """渲染结果按插入位置重定缩进基线（空白行不补缩进，避免尾随空白）。

    首行**不加**基线：岛从 token 起点截取，其行首缩进留在 water 前缀里（替换区间
    `[首 token, 末 token)` 不含行首空白）——首行再前缀会与 water 缩进叠加。
    """
    if not indent:
        return text
    lines = text.split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        out.append(line if not line.strip() else indent + line)
    return "\n".join(out)


def apply_edits(source: str, edits: list[tuple[int, int, str]]) -> str:
    """从右向左应用编辑集（edits 已按 start 升序、互不重叠）。"""
    out = source
    for start, end, replacement in sorted(edits, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out
