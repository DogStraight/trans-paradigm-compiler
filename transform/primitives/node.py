"""_ast.py — AST 操作原语

emit    根据规格创建 AST 节点
replace 替换父节点中的子节点
delete  删除节点（replace 的特化）
"""

from typing import Any
from core.define import Node
from .template import resolve_attrs, lookup_value


def emit(
    node_spec: dict[str, Any],
    context: dict[str, Any],
) -> Node:
    """根据规格创建 AST 节点

    支持格式:
        { "node": "NodeName", "attr1": "value1", "sub_node": [...] }
        { "node": "NodeName", "attrs": { "attr1": "value1", ... } }
        { "node_name": "NodeName", ... }   # node 的别名（兼容捕获数据形态）

    属性值支持:
        { "node": ..., ... }     — 子节点规格（递归 emit）
        { "ref": "path" }        — 从 context 原样透传值（不做模板字符串化）；
                                   值为 node_name/node 形态 dict 时递归重建
    """
    if isinstance(node_spec, str):
        return Node(node_spec)

    node_name = resolve_attrs(
        node_spec.get("node") or node_spec.get("node_name") or "", context
    )
    if not node_name:
        raise ValueError(f"emit: node_spec 缺少 'node' 字段: {node_spec}")

    raw_base = {k: v for k, v in node_spec.items() if k not in ("node", "node_name", "attrs")}
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
        elif isinstance(attr_val, dict) and "ref" in attr_val:
            # 原样透传：从 context 取原始值（不字符串化）。
            # 缺失 → 不设置该属性（渲染端 opt 对缺失属性跳过）。
            v = lookup_value(attr_val["ref"], context)
            if v is None:
                continue
            if isinstance(v, dict) and ("node" in v or "node_name" in v):
                v = emit(v, context)
            kwargs[attr_name] = v
        elif isinstance(attr_val, dict) and (
            "node" in attr_val or "node_name" in attr_val
        ):
            kwargs[attr_name] = emit(attr_val, context)
        elif isinstance(attr_val, list):
            kwargs[attr_name] = [
                (
                    emit(item, context)
                    if isinstance(item, dict) and ("node" in item or "node_name" in item)
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
