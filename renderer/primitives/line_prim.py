"""
line 原语 — 行布局（多个元素水平排列）

TOML 表示:
    { line = [
        "module ",
        { ref = "module_name" },
        { soft = true },
        " (",
        { ref = "ports" },
        ");",
    ] }

支持:
    soft / break 在 line 内控制换行点
    nest         额外缩进
    indent       soft/break 的附加缩进
"""

from typing import Any, Optional, List
from core.define import Node
from ..doc import Doc, Empty, Line as SoftLine, Break, Concat, Nest, group
from .registry import register


@register("line")
def eval_line(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Optional[Doc]:
    """求值 line 原语"""
    nest_level = expr.get("nest", 0)
    parts: List[Doc] = []
    pending_nest = 0
    has_soft = False

    for e in expr["line"]:
        if isinstance(e, dict) and (e.get("soft") or e.get("break")):
            indent_level = e.get("indent", 0)
            extra_indent = indent_level * len(renderer._INDENT_STR)
            if e.get("break"):
                parts.append(Break(extra_indent))
            else:
                parts.append(SoftLine(extra_indent))
            has_soft = True
            if indent_level > 0:
                pending_nest += extra_indent
        else:
            d = renderer._eval(e, node, indent, parent_layout)
            if d is not None:
                if not isinstance(d, Empty):
                    if pending_nest > 0:
                        d = Nest(pending_nest, d)
                        pending_nest = 0
                    parts.append(d)

    if not parts:
        return None

    doc: Doc = Concat(parts)
    if has_soft:
        doc = group(doc)
    if nest_level:
        doc = Nest(nest_level * len(renderer._INDENT_STR), doc)
    return doc
