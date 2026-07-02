"""
ref 原语 — 子节点引用

TOML 表示:
    { ref = "child_name" }

引用 AST 节点的某个字段，递归渲染该子节点。
支持单节点和列表。
"""

from typing import Any, Optional, List
from core.define import Node
from ..doc import Doc, Text, Concat, Empty
from .registry import register


@register("ref")
def eval_ref(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Optional[Doc]:
    """求值 ref 原语，ref 所在节点的 _error 也会渲染"""
    child = getattr(node, expr["ref"], None)

    parts: List[Doc] = []

    # ---- 主引用内容 ----
    if child is not None:
        if isinstance(child, Node):
            merged = renderer._get_merged_layout(parent_layout or {}, child.node_name)
            d = renderer._render_inline(child, merged, indent)
            if not isinstance(d, Empty):
                parts.append(d)

        elif isinstance(child, list):
            for item in child:
                if isinstance(item, Node):
                    merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
                    d = renderer._render_inline(item, merged, indent)
                else:
                    d = Text(str(item))
                if not isinstance(d, Empty):
                    parts.append(d)

        else:
            parts.append(Text(str(child)))

    # ---- _error（用 Error 节点的布局渲染）----
    err_node = getattr(node, "_error", None)
    if isinstance(err_node, Node):
        err_layout = renderer._layouts.get("Error", {})
        err_doc = renderer._render_inline(err_node, err_layout, indent)
        if not isinstance(err_doc, Empty):
            if parts:
                parts.append(Text(" "))
            parts.append(err_doc)

    return Concat(parts) if parts else None
