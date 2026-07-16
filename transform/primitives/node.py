"""_ast.py — AST 操作原语

emit    根据规格创建 AST 节点
replace 替换父节点中的子节点
delete  删除节点（replace 的特化）
"""

from typing import Any
from core.define import Node
from .template import resolve_attrs


def emit(
    node_spec: dict[str, Any],
    context: dict[str, Any],
) -> Node:
    """根据规格创建 AST 节点

    支持格式:
        { "node": "NodeName", "attr1": "value1", "sub_node": [...] }
        { "node": "NodeName", "attrs": { "attr1": "value1", ... } }
    """
    if isinstance(node_spec, str):
        return Node(node_spec)

    node_name = resolve_attrs(node_spec.get("node", ""), context)
    if not node_name:
        raise ValueError(f"emit: node_spec 缺少 'node' 字段: {node_spec}")

    raw_base = {k: v for k, v in node_spec.items() if k not in ("node", "attrs")}
    raw_attrs_nested = node_spec.get("attrs", {})
    if isinstance(raw_attrs_nested, dict):
        raw_base.update(raw_attrs_nested)
    resolved = resolve_attrs(raw_base, context)

    kwargs: dict[str, Any] = {}
    for attr_name, attr_val in resolved.items():
        if attr_name == "sub_node" and isinstance(attr_val, list):
            kwargs[attr_name] = [
                emit(item, context) if isinstance(item, dict) else item
                for item in attr_val
            ]
        elif isinstance(attr_val, dict) and "node" in attr_val:
            kwargs[attr_name] = emit(attr_val, context)
        elif isinstance(attr_val, list):
            kwargs[attr_name] = [
                (
                    emit(item, context)
                    if isinstance(item, dict) and "node" in item
                    else item
                )
                for item in attr_val
            ]
        else:
            kwargs[attr_name] = attr_val

    return Node(node_name, **kwargs)


def replace(
    old_node: Node,
    new_nodes: Node | list[Node] | None,
    parent: Node | None = None,
    parent_attr: str | None = None,
) -> list[Node]:
    """替换节点

    在父节点中定位 old_node 并将其替换为 new_nodes。
    new_nodes=None 表示删除。
    """
    if parent is None or parent_attr is None:
        if new_nodes is None:
            return []
        if isinstance(new_nodes, list):
            return new_nodes
        return [new_nodes]

    current = getattr(parent, parent_attr, None)
    if current is None:
        return []

    if isinstance(current, list):
        for i, item in enumerate(current):
            if item is old_node:
                if new_nodes is None:
                    current.pop(i)
                elif isinstance(new_nodes, list):
                    current[i : i + 1] = new_nodes
                else:
                    current[i] = new_nodes
                break
        setattr(parent, parent_attr, current)
    else:
        if new_nodes is None:
            setattr(parent, parent_attr, None)
        elif isinstance(new_nodes, list):
            setattr(parent, parent_attr, new_nodes[0] if new_nodes else None)
        else:
            setattr(parent, parent_attr, new_nodes)

    if new_nodes is None:
        return []
    if isinstance(new_nodes, list):
        return new_nodes
    return [new_nodes]


def delete(
    node: Node,
    parent: Node | None = None,
    parent_attr: str | None = None,
) -> list[Node]:
    """删除节点（replace 的特化）"""
    return replace(node, None, parent, parent_attr)
