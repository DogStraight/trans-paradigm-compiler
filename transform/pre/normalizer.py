"""
normalizer.py — 统一的 AST 规范化层

将 parser 原始输出翻译为规范 AST 形式，消除所有 parser 内部构造。
Renderer 仅依赖此规范形式。
"""

import tomllib
import os
from typing import Any, Optional
from core.define import Node

# 默认配置路径（位于 transform/config/）
_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "config", "normalize_config.toml"
)


def _load_config(config_path: Optional[str] = None) -> dict:
    """加载规范化配置"""
    path = config_path or _DEFAULT_CONFIG
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}


def normalize_ast(
    value: Any,
    layouts: Optional[dict] = None,
    config: Optional[dict] = None,
) -> Any:
    """递归规范化 AST，由 config 驱动，默认加载 normalize_config.toml"""
    if config is None:
        config = _load_config()

    extract_prefixes = config.get("extract_value", {}).get("prefixes", [])
    extract_names = set(config.get("extract_value", {}).get("names", []))
    eliminate_types = set(config.get("eliminate", {}).get("types", []))
    merge_attrs = config.get("merge", {}).get("attrs", [])
    flatten_types = set(config.get("flatten", {}).get("types", []))
    children_field = config.get("fields", {}).get("children", "sub_node")
    body_field = config.get("fields", {}).get("body", "body")

    return _normalize(
        value,
        layouts,
        config,
        extract_prefixes,
        extract_names,
        eliminate_types,
        merge_attrs,
        flatten_types,
        children_field,
        body_field,
    )


def _normalize(
    value,
    layouts,
    config,
    extract_prefixes,
    extract_names,
    eliminate_types,
    merge_attrs,
    flatten_types,
    children_field,
    body_field,
):
    """递归实现"""

    # ---- 新增：列表展平 ----
    if isinstance(value, list):
        result = []
        for item in value:
            normalized = _normalize(
                item,
                layouts,
                config,
                extract_prefixes,
                extract_names,
                eliminate_types,
                merge_attrs,
                flatten_types,
                children_field,
                body_field,
            )
            if normalized is not None:
                if isinstance(normalized, list):
                    result.extend(normalized)
                else:
                    result.append(normalized)
        return result

    if not isinstance(value, Node):
        return value

    node = value

    # 1. 按名称前缀/精确名提取字面值
    for prefix in extract_prefixes:
        if node.node_name.startswith(prefix):
            return getattr(node, "value", node.node_name)
    if node.node_name in extract_names:
        return getattr(node, "value", node.node_name)

    # 2. 消除包装节点（optional/repeat/sequence）
    if node.node_name in eliminate_types:
        if node.node_name == "optional":
            if (
                not hasattr(node, children_field)
                or getattr(node, children_field) is None
            ):
                return None
            sublist = getattr(node, children_field)
            if not sublist:
                return None
            # 可选节点只有一个子节点
            return _normalize(
                sublist[0],
                layouts,
                config,
                extract_prefixes,
                extract_names,
                eliminate_types,
                merge_attrs,
                flatten_types,
                children_field,
                body_field,
            )
        # repeat / sequence → 展平
        result = []
        if hasattr(node, children_field) and getattr(node, children_field) is not None:
            for child in getattr(node, children_field):
                normalized = _normalize(
                    child,
                    layouts,
                    config,
                    extract_prefixes,
                    extract_names,
                    eliminate_types,
                    merge_attrs,
                    flatten_types,
                    children_field,
                    body_field,
                )
                if normalized is not None:
                    if isinstance(normalized, list):
                        result.extend(normalized)
                    else:
                        result.append(normalized)
        # sequence 中的分隔符（逗号等）已被 extract_value 提取为字符串，
        # 注意：分隔列表由 _parse_repeat 的 separator 模式处理，不经过 seq 消除；
        # 纯 seq（如括号包裹）需要保留字符串项，不过滤。
        if node.node_name == "seq":
            pass  # 保留所有项（含字符串）
        return result

    # 3. 展开透明容器（Block 等）
    if node.node_name in flatten_types:
        body = getattr(node, children_field, None)
        if body is None:
            return []
        return _normalize(
            body,
            layouts,
            config,
            extract_prefixes,
            extract_names,
            eliminate_types,
            merge_attrs,
            flatten_types,
            children_field,
            body_field,
        )

    # 4. 普通节点：递归处理所有属性
    CORE_ATTRS = frozenset({"node_name", "start", "end"})
    for attr_name in list(vars(node)):
        if attr_name in CORE_ATTRS or attr_name.startswith("_"):
            continue
        val = getattr(node, attr_name)
        normalized = _normalize(
            val,
            layouts,
            config,
            extract_prefixes,
            extract_names,
            eliminate_types,
            merge_attrs,
            flatten_types,
            children_field,
            body_field,
        )
        if normalized is None:
            try:
                delattr(node, attr_name)
            except AttributeError:
                pass
        elif normalized is not val:
            setattr(node, attr_name, normalized)

    # 5. 合并命名属性到 children（first/rest 等）
    # 注意：不要预先创建 children_field，只在有需要时创建
    children = None
    if hasattr(node, children_field):
        children = getattr(node, children_field)

    for attr in merge_attrs:
        val = getattr(node, attr, None)
        if val is not None:
            if children is None:
                children = []
                setattr(node, children_field, children)
            if isinstance(val, list):
                children.extend(val)
            else:
                children.append(val)
            try:
                delattr(node, attr)
            except AttributeError:
                pass

    # 6. body_role = "flatten" → body 内容展开到 children_field
    if layouts:
        layout = layouts.get(node.node_name, {})
        body_cfg = layout.get("body", {})
        role = body_cfg.get("role") if isinstance(body_cfg, dict) else layout.get("body_role")
        if role == "flatten":
            body = getattr(node, body_field, None)
            if body is not None:
                if children is None:
                    children = []
                    setattr(node, children_field, children)
                if isinstance(body, list):
                    children.extend(body)
                elif isinstance(body, Node):
                    body_children = getattr(body, children_field, [])
                    if isinstance(body_children, list):
                        children.extend(body_children)
                    else:
                        children.append(body_children)
                # 从 children 中移除旧的 body 引用
                new_children = [c for c in children if c is not body]
                if new_children:
                    setattr(node, children_field, new_children)
                else:
                    # 如果清空了，删除该属性
                    if hasattr(node, children_field):
                        delattr(node, children_field)
                try:
                    delattr(node, body_field)
                except AttributeError:
                    pass

    # 7. 如果 children 存在但为空列表，则删除该属性
    if hasattr(node, children_field):
        children_val = getattr(node, children_field)
        if children_val is not None and len(children_val) == 0:
            delattr(node, children_field)

    # 8. wrap_single_stmts → 将 if/else 中非 begin/end 的语句体包裹在 BeginEnd 中
    if config.get("wrap_single_stmts", {}).get("enabled"):
        attr_map = config["wrap_single_stmts"].get("attr_map", {})
        if node.node_name in attr_map:
            for attr_name in attr_map[node.node_name]:
                body = getattr(node, attr_name, None)
                if not isinstance(body, Node):
                    continue
                inner = body
                if body.node_name == "Statement":
                    inner = getattr(body, "stmt", body)
                if isinstance(inner, Node) and inner.node_name != "BeginEnd":
                    be = Node("BeginEnd")
                    # 确保 be 有 sub_node 列表
                    if (
                        not hasattr(be, children_field)
                        or getattr(be, children_field) is None
                    ):
                        setattr(be, children_field, [])
                    getattr(be, children_field).append(body)
                    setattr(node, attr_name, be)

    return node
