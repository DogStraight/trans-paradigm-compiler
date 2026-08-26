"""line 原语 — 行布局

Doc: docs/renderer_architecture.md（Line/Break 换行原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Empty, Text, Line as SoftLine, Break, Concat, Nest, group
from .registry import register


@register("line")
def eval_line(expr: dict, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc | None:
    nest_level = expr.get("nest", 0)
    parts: list[Doc] = []
    pending_nest = 0
    has_soft = False

    # 行中注释 token 标注定位（注释节点模型 2b-2）：inline_after = {锚 token:
    # [(注释, 源行号)]}，锚 token 是注释前的 token（如 `assign b = /* c */ rst_n`
    # 的 `=`）。在布局 line 元素序列里，遇到含锚 token 的文本元素 → 后插注释
    # （`=` 后输出）。消费后**删除节点槽位**（pipeline 兜底靠"残留判断"防双份）。
    node_slots = getattr(node, "_comment_slots", None) or {}
    ia_slots: dict = node_slots.get("inline_after", {}) or {}

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
                # 文本元素含锚 token → 后插行中注释
                if isinstance(e, str) and ia_slots:
                    for anchor, entries in list(ia_slots.items()):
                        if anchor in e:
                            for text, _line in entries:
                                parts.append(Text(text))
                                parts.append(Text(" "))
                            del ia_slots[anchor]
                            break

    if not parts:
        return None

    doc: Doc = Concat(parts)
    if has_soft:
        doc = group(doc)
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc
