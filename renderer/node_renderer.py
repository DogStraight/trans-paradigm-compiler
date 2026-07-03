"""
node_renderer.py — AST 节点级渲染逻辑

将单个 AST 节点渲染为 Doc IR，处理 head/body/tail 三段式布局。
"""

from typing import Any, Optional, List
from core.define import Node
from .doc import Doc, Empty, Text, Break, Concat, Nest
from .primitives import eval_expr


def render_node(
    node: Node,
    layout: dict,
    indent: int,
    renderer: Any,
) -> Doc:
    """渲染节点为独立块

    不再通过 Prefix 添加第一行缩进；body 的缩进由调用方
    （render_node / render_inline 的 body 渲染段）通过
    Break(4) + Nest(4, child_doc) 统一控制。

    Args:
        node: 当前 AST 节点
        layout: 该节点的布局配置
        indent: 当前缩进层级（仅用于传递，不用于 Prefix）
        renderer: Renderer 实例

    Returns:
        Doc IR
    """
    head_expr = layout.get("layout") or layout.get("head")
    body_cfg = layout.get("body")
    tail_cfg = layout.get("tail")
    indent_spaces = len(renderer._INDENT_STR)

    parts: List[Doc] = []

    # --- head ---
    if head_expr:
        head_doc = eval_expr(head_expr, node, indent, layout, renderer)
        if head_doc is not None:
            parts.append(head_doc)

    # --- body ---
    if body_cfg:
        body_docs = render_body(node, indent + 1, body_cfg, layout, renderer)
        for bd in body_docs:
            parts.append(Break(indent_spaces))
            parts.append(Nest(indent_spaces, bd))

    # --- tail ---
    tail_doc = None
    tb = 0
    if isinstance(tail_cfg, str):
        tail_doc = Text(tail_cfg) if tail_cfg else None
        tb = layout.get("tail_break", 0)
    elif isinstance(tail_cfg, dict):
        if "text" in tail_cfg:
            tail_doc = Text(tail_cfg["text"]) if tail_cfg.get("text") else None
            tb = tail_cfg.get("break", 0)
        else:
            tail_doc = eval_expr(tail_cfg, node, indent, layout, renderer)
            tb = layout.get("tail_break", 0)
    if tail_doc is not None:
        tb = layout.get("tail_break", tb)
        if isinstance(tb, bool):
            tb = 1 if tb else 0
        parts.append(Break())
        parts.append(tail_doc)
        for _ in range(tb - 1):
            parts.append(Break())

    if parts:
        return Concat(parts)
    return Empty()


def render_inline(
    node: Node,
    layout: dict,
    indent: int,
    renderer: Any,
) -> Doc:
    """内联渲染节点（用于 ref 在 line/group/join 中引用子节点时）

    与 render_node 逻辑相同（都不加 Prefix），
    区别只是语义上用于内联上下文，但实现已一致。
    """
    head_expr = layout.get("layout") or layout.get("head")
    body_cfg = layout.get("body")
    tail_cfg = layout.get("tail")
    indent_spaces = len(renderer._INDENT_STR)

    parts: List[Doc] = []

    # --- head（内联：不加前缀）---
    if head_expr:
        head_doc = eval_expr(head_expr, node, indent, layout, renderer)
        if head_doc is not None:
            parts.append(head_doc)

    # --- body ---
    if body_cfg:
        body_docs = render_body(node, indent + 1, body_cfg, layout, renderer)
        for bd in body_docs:
            parts.append(Break(indent_spaces))
            parts.append(Nest(indent_spaces, bd))

    # --- tail ---
    tail_doc = None
    tb = 0
    if isinstance(tail_cfg, str):
        tail_doc = Text(tail_cfg) if tail_cfg else None
        tb = layout.get("tail_break", 0)
    elif isinstance(tail_cfg, dict):
        if "text" in tail_cfg:
            tail_doc = Text(tail_cfg["text"]) if tail_cfg.get("text") else None
            tb = tail_cfg.get("break", 0)
        else:
            tail_doc = eval_expr(tail_cfg, node, indent, layout, renderer)
            tb = layout.get("tail_break", 0)
    if tail_doc is not None:
        tb = layout.get("tail_break", tb)
        if isinstance(tb, bool):
            tb = 1 if tb else 0
        parts.append(Break())
        parts.append(tail_doc)
        for _ in range(tb - 1):
            parts.append(Break())

    if parts:
        return Concat(parts)
    return Empty()


def render_body(
    node: Node,
    indent: int,
    body_cfg: Optional[dict],
    parent_layout: Optional[dict],
    renderer: Any,
) -> List[Doc]:
    """渲染节点主体：遍历子节点，每个缩进一行

    body_cfg 可指定 source 字段名（如 source = "items"），
    或 items 列表（如 items = ["then_stmt", "else_chain"]），
    从 node 的对应属性获取子节点。
    """
    if body_cfg and isinstance(body_cfg, dict):
        source = body_cfg.get("source")
        items_list = body_cfg.get("items")
    else:
        source = None
        items_list = None

    children_field = renderer._children_field

    if items_list:
        # 具名属性列表：按顺序从 node 提取子节点
        children: List[Node] = []
        for attr_name in items_list:
            val = getattr(node, attr_name, None)
            if val is None:
                continue
            if isinstance(val, Node):
                children.append(val)
            elif isinstance(val, list):
                children.extend(v for v in val if isinstance(v, Node))
    elif source:
        container = getattr(node, source, None)
        if isinstance(container, Node):
            # 优先使用与 source 同名的属性（如 CaseItemList.items），
            # 再回退到 children_field（如 Block.sub_node）
            children = getattr(container, source, None) or getattr(
                container, children_field, []
            )
        elif isinstance(container, list):
            children = container
        else:
            children = []
    else:
        children = getattr(node, children_field, [])

    docs: List[Doc] = []
    children_list = [c for c in children if isinstance(c, Node)]
    for i, child in enumerate(children_list):
        merged = renderer._get_merged_layout(parent_layout or {}, child.node_name)
        d = render_node(child, merged, indent, renderer)
        if not isinstance(d, Empty):
            if body_cfg and isinstance(body_cfg, dict):
                sep = body_cfg.get("sep")
                if sep and i < len(children_list) - 1:
                    d = Concat([d, Text(sep)])
            docs.append(d)
    return docs


def resolve_items(
    node: Node,
    items_spec: Optional[str],
    renderer: Any,
) -> List[Any]:
    """解析 items 引用

    未指定时 → node.{children_field}
    字段名 → 对应属性
    """
    if not items_spec:
        return getattr(node, renderer._children_field, [])
    attr = getattr(node, items_spec, None)
    if attr is None:
        return []
    if isinstance(attr, list):
        return attr
    return [attr]
