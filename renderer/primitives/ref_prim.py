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
    """求值 ref 原语"""
    child = getattr(node, expr["ref"], None)
    if child is None:
        return None

    # ---- 单 Node ----
    if isinstance(child, Node):
        base_layout = renderer._layouts.get(child.node_name, {})
        override = (
            (parent_layout or {}).get("override", {}).get(child.node_name, {})
        )
        merged = dict(base_layout)
        merged.update(override)
        return renderer._render_inline(child, merged, indent)

    # ---- Node 列表 ----
    if isinstance(child, list):
        docs: List[Doc] = []
        for item in child:
            if isinstance(item, Node):
                item_layout = renderer._layouts.get(item.node_name, {})
                item_override = (
                    (parent_layout or {})
                    .get("override", {})
                    .get(item.node_name, {})
                )
                merged_item = dict(item_layout)
                merged_item.update(item_override)
                d = renderer._render_inline(item, merged_item, indent)
            else:
                d = Text(str(item))
            if not isinstance(d, Empty):
                docs.append(d)
        return Concat(docs) if docs else None

    # ---- 标量值 ----
    return Text(str(child))
