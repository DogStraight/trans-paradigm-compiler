"""
normalizer.py — 统一的 AST 规范化层

将 parser 原始输出翻译为规范 AST 形式，消除所有 parser 内部构造。
Renderer 仅依赖此规范形式。

重要约定：
- 只消除解析器内部引入的包装结构：optional、repeat、seq
- 语法层结构（如 DeclaratorList、Statement 等）一律保留，不被消除
- 所有消除逻辑在代码内部硬编码，不再依赖外部 TOML 配置
"""

import tomllib
import os
from typing import Any, Optional
from core.define import Node

# 默认配置路径（保留以兼容旧逻辑，但核心消除集合已在代码中硬编码）
_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "config", "normalize_config.toml"
)


def _load_config(config_path: Optional[str] = None) -> dict:
    """加载规范化配置（仅用于 merge_attrs / flatten_types 等辅助配置）"""
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
    """
    递归规范化 AST。

    核心消除集合（硬编码，不依赖配置文件）：
        optional, repeat, seq  ← 仅这些是 parser 内部包装结构
    注意：DeclaratorList 是语法层结构，坚决不消除。
    """
    if config is None:
        config = _load_config()

    # ===== 核心消除集合（只消除 parser 内部结构）=====
    # optional  → 空值过滤
    # repeat    → 零次或多次重复（展开为列表）
    # seq       → 序列（展开为列表）
    # 注意：语法层结构（如 DeclaratorList）不在这里，保留原样
    ELIMINATE_TYPES = {"optional", "repeat", "seq"}

    # 从 TOML 加载额外配置（合并属性、展平透明容器等）
    extract_prefixes = config.get("extract_value", {}).get("prefixes", [])
    extract_names = set(config.get("extract_value", {}).get("names", []))
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
        ELIMINATE_TYPES,
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

    # ---- 列表展平 ----
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

    # 1. 按名称前缀/精确名提取字面值（用于 token 节点归一化）
    for prefix in extract_prefixes:
        if node.node_name.startswith(prefix):
            return getattr(node, "value", node.node_name)
    if node.node_name in extract_names:
        return getattr(node, "value", node.node_name)

    # 2. 消除包装节点（仅限 optional / repeat / seq，不碰语法层结构）
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

        # repeat / seq → 展平子节点列表
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

        if not result:
            return None
        if len(result) == 1:
            return result[0]
        return result

    # 3. 展开透明容器（如 Block 等，由 TOML 配置驱动）
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

    # 4. 普通节点（含语法层结构如 DeclaratorList）：递归处理所有属性
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

    # 5. 合并命名属性到 children（仅用于特定语法结构）
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

    # 6. body_role = "flatten" 处理（由渲染器布局配置驱动）
    if layouts:
        layout = layouts.get(node.node_name, {})
        body_cfg = layout.get("body", {})
        role = (
            body_cfg.get("role")
            if isinstance(body_cfg, dict)
            else layout.get("body_role")
        )
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
                # 移除旧的 body 引用
                new_children = [c for c in children if c is not body]
                if new_children:
                    setattr(node, children_field, new_children)
                elif hasattr(node, children_field):
                    delattr(node, children_field)
                try:
                    delattr(node, body_field)
                except AttributeError:
                    pass

    # 7. 如果 children 为空列表，删除该属性
    if hasattr(node, children_field):
        children_val = getattr(node, children_field)
        if children_val is not None and len(children_val) == 0:
            delattr(node, children_field)

    # 8. wrap_single_stmts（单语句包裹 BeginEnd，由 TOML 配置驱动）
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
                    if (
                        not hasattr(be, children_field)
                        or getattr(be, children_field) is None
                    ):
                        setattr(be, children_field, [])
                    getattr(be, children_field).append(body)
                    setattr(node, attr_name, be)

    return node
