"""ref 原语 — 子节点引用

Doc: renderer/renderer_architecture.md（ref 节点引用原语）
"""
from typing import Any, List
from core.define import Node
from ..doc import Doc, Text, Concat, Empty
from .registry import register


@register("ref")
def eval_ref(expr: dict, node: Node, parent_layout: dict | None,
             renderer: Any) -> Doc | None:
    """ref 原语：子节点引用。

    引用值三类：Node → 按布局 inline 渲染；list → 逐项渲染（节点走布局、
    非节点文本化）；标量 → 文本。另附 `_error`（解析恢复节点）的渲染尾。
    """
    parts: List[Doc] = []
    _collect_child_parts(parts, getattr(node, expr["ref"], None), parent_layout, renderer)
    _collect_error_part(parts, node, renderer)
    return Concat(parts) if parts else None


def _collect_child_parts(
    parts: List[Doc], child, parent_layout: dict | None, renderer: Any
) -> None:
    """引用值 → parts（保持原始顺序；Empty 不入列）。"""
    if child is None:
        return
    if isinstance(child, Node):
        parts.extend(_inline_docs(child, parent_layout, renderer))
        return
    if isinstance(child, list):
        for item in child:
            if isinstance(item, Node):
                parts.extend(_inline_docs(item, parent_layout, renderer))
            else:
                parts.append(Text(str(item)))
        return
    parts.append(Text(str(child)))


def _inline_docs(
    child: Node, parent_layout: dict | None, renderer: Any
) -> List[Doc]:
    """节点 inline 渲染 → doc 列表（Empty 视为无内容，返回空列表）。"""
    merged = renderer._get_merged_layout(parent_layout or {}, child.node_name)
    d = renderer._render_inline(child, merged)
    return [] if isinstance(d, Empty) else [d]


def _collect_error_part(parts: List[Doc], node: Node, renderer: Any) -> None:
    """`_error`（解析恢复节点）用 Error 节点布局渲染；前有内容时隔一个空格。"""
    err_node = getattr(node, "_error", None)
    if not isinstance(err_node, Node):
        return
    err_doc = renderer._render_inline(err_node, renderer._layouts.get("Error", {}))
    if isinstance(err_doc, Empty):
        return
    if parts:
        parts.append(Text(" "))
    parts.append(err_doc)
