"""line 原语 — 行布局

Doc: docs/renderer_architecture.md（Line/Break 换行原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Empty, Line as SoftLine, Break, Concat, Nest, group
from .registry import register


@register("line")
def eval_line(expr: dict, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc | None:
    nest_level = expr.get("nest", 0)
    parts: list[Doc] = []
    pending_nest = 0
    has_soft = False

    for e in expr["line"]:
        if isinstance(e, dict) and (e.get("soft") or e.get("break")):
            indent_level = e.get("indent", 0)
            extra_indent = renderer._indent(indent_level)
            if e.get("break"):
                parts.append(Break(extra_indent))
            else:
                parts.append(SoftLine(extra_indent))
            has_soft = True
            if indent_level > 0:
                pending_nest += extra_indent
        else:
            d = renderer._eval(e, node, parent_layout)
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
        doc = Nest(renderer._indent(nest_level), doc)
    return doc
