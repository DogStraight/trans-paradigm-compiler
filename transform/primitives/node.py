"""node.py — AST 操作原语

emit    根据规格创建 AST 节点
replace 替换父节点中的子节点
delete  删除节点（replace 的特化）
Doc: docs/language_walkthrough.md（节点操作变换原语）
"""

from typing import Any
from core.define import Node
from .template import resolve_attrs, lookup_value


# `{"ref": ...}` 取值缺失的哨兵：与"属性值本来就是 None"区分开（前者不设属性）
_MISSING = object()


def _node_name_of(node_spec: dict, context: dict) -> str:
    """规格里的节点名（`node` / 别名 `node_name`；解析模板后）。"""
    return resolve_attrs(
        node_spec.get("node") or node_spec.get("node_name") or "", context
    )


def _raw_attrs(node_spec: dict) -> dict:
    """规格 → 原始属性表（`attrs` 子表并入；node/node_name/attrs 三键不算属性）。"""
    raw = {
        k: v for k, v in node_spec.items() if k not in ("node", "node_name", "attrs")
    }
    nested = node_spec.get("attrs", {})
    if isinstance(nested, dict):
        raw.update(nested)
    return raw


def _emit_sub_nodes(attr_val: list, context: dict) -> list:
    """`sub_node`：列表内**任何** dict 都是节点规格（递归 emit）。"""
    return [
        emit(item, context) if isinstance(item, dict) else item for item in attr_val
    ]


def _emit_list(attr_val: list, context: dict) -> list:
    """列表属性值：dict 且带 node/node_name 者递归 emit，其余原样。"""
    return [
        (
            emit(item, context)
            if isinstance(item, dict) and ("node" in item or "node_name" in item)
            else item
        )
        for item in attr_val
    ]


def _resolve_ref(ref: Any, context: dict) -> Any:
    """`{"ref": "path"}` → context 原值（值为节点规格 dict 时递归重建）。"""
    v = lookup_value(ref, context)
    if isinstance(v, dict) and ("node" in v or "node_name" in v):
        return emit(v, context)
    return v


def _emit_attr(attr_name: str, attr_val: Any, context: dict) -> Any:
    """单个属性值 → 节点 kwargs 值；`_MISSING` = 不设置该属性。

    值形态分派：`sub_node` 列表 / `{"ref": ...}` 原样透传 / 节点规格 dict /
    列表 / 标量原样。
    """
    if attr_name == "sub_node" and isinstance(attr_val, list):
        return _emit_sub_nodes(attr_val, context)
    if isinstance(attr_val, dict) and "ref" in attr_val:
        # 原样透传：从 context 取原始值（不字符串化）。
        # 缺失 → 不设置该属性（渲染端 opt 对缺失属性跳过）。
        v = _resolve_ref(attr_val["ref"], context)
        return _MISSING if v is None else v
    if isinstance(attr_val, dict) and ("node" in attr_val or "node_name" in attr_val):
        return emit(attr_val, context)
    if isinstance(attr_val, list):
        return _emit_list(attr_val, context)
    return attr_val


def emit(
    node_spec: dict[str, Any],
    context: dict[str, Any],
) -> Node:
    """根据规格创建 AST 节点

    支持格式:
        { "node": "NodeName", "attr1": "value1", "sub_node": [...] }
        { "node": "NodeName", "attrs": { "attr1": "value1", ... } }
        { "node_name": "NodeName", ... }   # node 的别名（兼容捕获数据形态）

    属性值支持（逐形态分派见 `_emit_attr`）:
        { "node": ..., ... }     — 子节点规格（递归 emit）
        { "ref": "path" }        — 从 context 原样透传值（不做模板字符串化）；
                                   值为 node_name/node 形态 dict 时递归重建
    """
    if isinstance(node_spec, str):
        return Node(node_spec)

    node_name = _node_name_of(node_spec, context)
    if not node_name:
        raise ValueError(f"emit: node_spec 缺少 'node' 字段: {node_spec}")

    resolved = resolve_attrs(_raw_attrs(node_spec), context)
    kwargs: dict[str, Any] = {}
    for attr_name, attr_val in resolved.items():
        value = _emit_attr(attr_name, attr_val, context)
        if value is not _MISSING:
            kwargs[attr_name] = value
    return Node(node_name, **kwargs)


def _replacement_list(new_nodes: Node | list[Node] | None) -> list[Node]:
    """替换结果列表形态（None → 空；单节点 → 单元素列表；列表原样）。"""
    if new_nodes is None:
        return []
    if isinstance(new_nodes, list):
        return new_nodes
    return [new_nodes]


def _replace_in_list(current: list, old_node: Node, new_nodes) -> list:
    """列表属性：按身份定位后原址替换（None → pop；列表 → 切片替换）。"""
    for i, item in enumerate(current):
        if item is not old_node:
            continue
        if new_nodes is None:
            current.pop(i)
        elif isinstance(new_nodes, list):
            current[i : i + 1] = new_nodes
        else:
            current[i] = new_nodes
        break
    return current


def _replace_in_scalar(new_nodes) -> Node | None:
    """标量属性：单节点直赋；列表取首元素（空列表 → None）；None → 清空。"""
    if new_nodes is None:
        return None
    if isinstance(new_nodes, list):
        return new_nodes[0] if new_nodes else None
    return new_nodes


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
        return _replacement_list(new_nodes)

    current = getattr(parent, parent_attr, None)
    if current is None:
        return []

    if isinstance(current, list):
        setattr(parent, parent_attr, _replace_in_list(current, old_node, new_nodes))
    else:
        setattr(parent, parent_attr, _replace_in_scalar(new_nodes))

    return _replacement_list(new_nodes)


def delete(
    node: Node,
    parent: Node | None = None,
    parent_attr: str | None = None,
) -> list[Node]:
    """删除节点（replace 的特化）"""
    return replace(node, None, parent, parent_attr)
