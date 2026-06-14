"""
normalizer.py — 统一的 AST 规范化层

将 parser 原始输出翻译为规范 AST 形式，消除所有 parser 内部构造。
Renderer 仅依赖此规范形式。
所有规则通过 normalize_config.toml 配置，零硬编码。
"""

import tomllib
import os
from typing import Any, Optional
from core.define import Node

# 默认配置路径（相对于本文件）
_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "normalize_config.toml")


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
    if not isinstance(value, Node):
        if isinstance(value, list):
            return [
                _normalize(
                    v,
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
                for v in value
            ]
        return value

    node = value

    # 1. 按名称前缀/精确名提取字面值
    for prefix in extract_prefixes:
        if node.name.startswith(prefix):
            return getattr(node, "value", node.name)
    if node.name in extract_names:
        return getattr(node, "value", node.name)

    # 2. 消除包装节点（optional/repeat/sequence）
    if node.name in eliminate_types:
        if node.name == "optional":
            if not node.sub_node:
                return None
            return _normalize(
                node.sub_node[0],
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
        for child in node.sub_node:
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
        # 过滤掉非 Node 项，避免与 layout 的 join 分隔符冲突
        if node.name == "sequence":
            result = [x for x in result if isinstance(x, Node)]
        return result

    # 3. 展开透明容器（Block 等）
    if node.name in flatten_types:
        return _normalize(
            node.sub_node,
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
    CORE_ATTRS = frozenset({"name", "start", "end"})
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
    for attr in merge_attrs:
        val = getattr(node, attr, None)
        if val is not None:
            children = getattr(node, children_field, [])
            if isinstance(val, list):
                children.extend(val)
            else:
                children.append(val)
            try:
                delattr(node, attr)
            except AttributeError:
                pass

    # 6. body_role = "flatten" → body 内容展开到 sub_node
    if layouts:
        role = layouts.get(node.name, {}).get("body_role")
        if role == "flatten":
            body = getattr(node, body_field, None)
            if isinstance(body, list):
                # body 已被归一化（Block 展平为列表）
                getattr(node, children_field).extend(body)
            elif isinstance(body, Node):
                # 非 Block 类型的 body，取其子节点
                for child in getattr(body, children_field, []):
                    if isinstance(child, Node):
                        getattr(node, children_field).append(child)
            if body is not None:
                # 从 sub_node 中移除旧的 body 引用
                setattr(
                    node,
                    children_field,
                    [c for c in getattr(node, children_field) if c is not body],
                )
                try:
                    delattr(node, body_field)
                except AttributeError:
                    pass

    # 7. wrap_single_stmts → 将 if/else 中非 begin/end 的语句体包裹在 BeginEnd 中
    if config.get("wrap_single_stmts", {}).get("enabled"):
        attr_map = config["wrap_single_stmts"].get("attr_map", {})
        if node.name in attr_map:
            for attr_name in attr_map[node.name]:
                body = getattr(node, attr_name, None)
                if not isinstance(body, Node):
                    continue
                # 检查是否是 Statement 内含非 BeginEnd 的语句
                inner = body
                if body.name == "Statement":
                    inner = getattr(body, "stmt", body)
                if isinstance(inner, Node) and inner.name != "BeginEnd":
                    be = Node("BeginEnd")
                    be.sub_node.append(body)
                    setattr(node, attr_name, be)

    return node
