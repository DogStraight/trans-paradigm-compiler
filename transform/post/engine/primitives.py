"""
primitives.py — Transform 原语操作

提供配置驱动变换所需的所有基础构建块：
    lookup     查表（类型定义、符号表等）
    foreach    遍历列表
    emit       创建 AST 节点
    replace    替换节点
    delete     删除节点
    condition  条件守卫

每个原语都是纯函数，不持有状态。
"""

import re
from typing import Any, Optional, Callable
from core.define import Node


# ── 模板字符串解析 ──

_TEMPLATE_RE = re.compile(r"\{([^}]+)\}")


def resolve_template(template: str, context: dict[str, Any]) -> str:
    """解析模板字符串 {attr.sub_attr}，从 context 中取值

    支持:
        {name}            → context["name"]
        {a.b.c}           → context["a"]["b"]["c"]
        {a[0].b}          → context["a"][0]["b"]
        {signal.name}     → context["signal"]["name"]

    未匹配的占位符保留原样。
    """
    def _lookup(path: str, ctx: dict) -> str:
        parts = re.split(r'\.|\[|\]', path)
        parts = [p for p in parts if p]
        val: Any = ctx
        try:
            for p in parts:
                if isinstance(val, dict):
                    val = val[p]
                elif isinstance(val, list):
                    val = val[int(p)]
                elif hasattr(val, p):
                    val = getattr(val, p)
                elif hasattr(val, "__getitem__"):
                    val = val[p]
                else:
                    return "{" + path + "}"
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            return "{" + path + "}"
        return str(val) if not isinstance(val, (Node, dict, list)) else "{" + path + "}"

    return _TEMPLATE_RE.sub(lambda m: _lookup(m.group(1), context), template)


def resolve_attrs(
    attrs: Any,
    context: dict[str, Any],
) -> Any:
    """递归解析属性字典/列表中的模板字符串"""
    if isinstance(attrs, str):
        return resolve_template(attrs, context)
    if isinstance(attrs, dict):
        return {k: resolve_attrs(v, context) for k, v in attrs.items()}
    if isinstance(attrs, list):
        return [resolve_attrs(item, context) for item in attrs]
    return attrs


# ── 原语: lookup ──

def lookup(
    table: dict[str, Any],
    key_template: str,
    context: dict[str, Any],
) -> Any:
    """从 table 中查找 key 对应的数据

    Args:
        table:        数据表 dict
        key_template: 键模板，例如 "{type_spec.type_name}.{type_spec.role_name}"
        context:      当前上下文（节点属性 + foreach 变量）
    Returns:
        查找到的数据，未找到时返回 None
    """
    key = resolve_template(key_template, context)
    # 支持嵌套 key: "spi.master" → table["spi"]["master"]
    parts = key.split(".")
    val: Any = table
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return None
        if val is None:
            return None
    return val


def lookup_scope(
    scope: Any,
    key_template: str,
    context: dict[str, Any],
) -> Any:
    """从 Scope 作用域链中按名称查找符号

    支持模板 key："{name}" → scope.resolve(name)
    也支持 "{name}.attr" → symbol.attrs["attr"] 链式访问

    Args:
        scope:        语义分析产出的根 Scope 对象
        key_template: 键模板，例如 "{id_name}" 或 "{id_name}.width"
        context:      当前上下文
    Returns:
        查找到的符号 dict（含 name/kind/attrs），未找到返回 None
    """
    key = resolve_template(key_template, context)
    # 分离符号名与属性路径："sig_name.width" → name="sig_name", attr_path=["width"]
    parts = key.split(".")
    sym_name = parts[0]
    attr_path = parts[1:]

    if not hasattr(scope, "resolve"):
        return None
    sym = scope.resolve(sym_name)
    if sym is None:
        return None

    # 有属性路径 → 从 attrs 或 Symbol 自身字段取值
    if attr_path:
        val: Any = sym
        for attr in attr_path:
            if hasattr(val, attr):
                val = getattr(val, attr)
            elif isinstance(val, dict) and attr in val:
                val = val[attr]
            else:
                return None
        return val if isinstance(val, (str, int, float, bool, list)) else None

    # 返回符号的 dict 形式（供模板引用其字段：{sym.name} {sym.kind}）
    return {"name": sym.name, "kind": sym.kind, **sym.attrs}


# ── 原语: lookup_type_scope ──

def lookup_type_scope(
    root_scope: Any,
    key_template: str,
    context: dict[str, Any],
) -> Any:
    """从 scope 作用域链中按类型作用域 + 角色名查找

    专用于 EXT 类型系统：TypeDecl 在 scope 中创建 type 子作用域，
    其下 role 符号存储了 ports 信息。

    Key 语法: "type_name.role_name" → 先找 type 子域，再找 role 符号
    例如: "spi.master" → root_scope.find_child_scope("spi", "type")
                             → type_scope.resolve("master")
                             → Symbol.attrs (含 ports)

    Args:
        root_scope: 语义分析产出的根 Scope 对象
        key_template: 键模板，例如 "{type_spec.type_name}.{type_spec.role_name}"
        context: 当前上下文（节点属性）
    Returns:
        角色符号的 attrs dict（含 ports 等），未找到返回 None
    """
    from analyzer.scope import Scope as ScopeType
    key = resolve_template(key_template, context)
    parts = key.split(".")
    if len(parts) < 2:
        return None
    type_name = parts[0]
    role_name = parts[1]
    attr_path = parts[2:] if len(parts) > 2 else []

    if not hasattr(root_scope, "find_child_scope"):
        return None

    # 1. 查找 type 子作用域
    type_scope = root_scope.find_child_scope(type_name, "type")
    if type_scope is None:
        return None

    # 2. 在类型作用域中查找角色符号
    role_sym = type_scope.resolve(role_name)
    if role_sym is None:
        return None

    # 3. 有属性路径 → 从 attrs 取
    if attr_path:
        val: Any = role_sym.attrs
        for attr in attr_path:
            if isinstance(val, dict) and attr in val:
                val = val[attr]
            else:
                return None
        return val

    # 4. 返回角色符号的完整 attrs
    return {
        "name": role_sym.name,
        "kind": role_sym.kind,
        **role_sym.attrs,
    }


# ── 原语: foreach ──

def foreach(
    items: list[Any],
    as_name: str,
    callback: Callable[[Any, dict[str, Any]], Any],
    outer_context: dict[str, Any],
) -> list[Any]:
    """遍历列表，对每个元素执行 callback

    Args:
        items:          要遍历的列表
        as_name:        元素在上下文中的变量名
        callback:       回调 fn(item, context) → 产出
        outer_context:  外层上下文
    Returns:
        所有 callback 产出的列表（扁平化）
    """
    results: list[Any] = []
    for item in items:
        item_ctx = dict(outer_context)
        item_ctx[as_name] = item
        result = callback(item, item_ctx)
        if isinstance(result, list):
            results.extend(result)
        elif result is not None:
            results.append(result)
    return results


# ── 原语: emit ──

def emit(
    node_spec: dict[str, Any],
    context: dict[str, Any],
) -> Node:
    """根据规格创建 AST 节点

    支持两种格式：

    1. 扁平格式（推荐）:
        { "node": "NodeName", "attr1": "value1", "sub_node": [...] }

    2. 嵌套格式（兼容）:
        { "node": "NodeName", "attrs": { "attr1": "value1", ... } }

    "attrs" 如果存在，其内容会被合并到顶层。
    模板字符串 {expr} 会被自动解析。
    sub_node 支持嵌套 emit 规格。
    """
    if isinstance(node_spec, str):
        return Node(node_spec)

    node_name = node_spec.get("node", "")
    if not node_name:
        raise ValueError(f"emit: node_spec 缺少 'node' 字段: {node_spec}")

    # 合并 attrs 嵌套到顶层
    raw_base = {k: v for k, v in node_spec.items() if k not in ("node", "attrs")}
    raw_attrs_nested = node_spec.get("attrs", {})
    if isinstance(raw_attrs_nested, dict):
        raw_base.update(raw_attrs_nested)
    resolved = resolve_attrs(raw_base, context)

    # 递归处理 sub_node 中的嵌套 emit 规格
    kwargs: dict[str, Any] = {}
    for attr_name, attr_val in resolved.items():
        if attr_name == "sub_node" and isinstance(attr_val, list):
            kwargs[attr_name] = [
                emit(item, context) if isinstance(item, dict) else item
                for item in attr_val
            ]
        else:
            kwargs[attr_name] = attr_val

    return Node(node_name, **kwargs)


# ── 原语: replace ──

def replace(
    old_node: Node,
    new_nodes: Node | list[Node] | None,
    parent: Optional[Node] = None,
    parent_attr: Optional[str] = None,
) -> list[Node]:
    """替换节点

    在父节点中定位 old_node 并将其替换为 new_nodes。

    Args:
        old_node:   旧节点
        new_nodes:  新节点（单个 / 列表 / None=删除）
        parent:     父节点（若不提供则只返回 new_nodes）
        parent_attr:父节点中持有 old_node 的属性名
    Returns:
        替换后的新节点列表
    """
    if parent is None or parent_attr is None:
        # 无父节点上下文，直接返回
        if new_nodes is None:
            return []
        if isinstance(new_nodes, list):
            return new_nodes
        return [new_nodes]

    current = getattr(parent, parent_attr, None)
    if current is None:
        return []

    if isinstance(current, list):
        # 在列表中查找并替换
        for i, item in enumerate(current):
            if item is old_node:
                if new_nodes is None:
                    current.pop(i)
                elif isinstance(new_nodes, list):
                    current[i:i+1] = new_nodes
                else:
                    current[i] = new_nodes
                break
        setattr(parent, parent_attr, current)
    else:
        # 单值属性
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


# ── 原语: delete ──

def delete(
    node: Node,
    parent: Optional[Node] = None,
    parent_attr: Optional[str] = None,
) -> list[Node]:
    """删除节点（replace 的特化）"""
    return replace(node, None, parent, parent_attr)


# ── 原语: condition ──

def condition(
    predicate: Callable[[dict[str, Any]], bool],
    context: dict[str, Any],
) -> bool:
    """条件守卫：谓词为真时继续变换"""
    return predicate(context)


def make_exists_condition(path: str) -> Callable[[dict[str, Any]], bool]:
    """创建 '属性存在' 条件

    Args:
        path: 属性路径，如 "type_spec.type_name"
    Returns:
        谓词函数
    """
    def _pred(ctx: dict) -> bool:
        parts = path.split(".")
        val: Any = ctx
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            elif hasattr(val, p):
                val = getattr(val, p)
            else:
                return False
            if val is None:
                return False
        return True
    return _pred
