"""
normalizer.py — 统一的 AST 规范化层

将 parser 原始输出翻译为规范 AST 形式，消除所有 parser 内部构造。
Renderer 仅依赖此规范形式。

重要约定：
- 只消除解析器内部引入的包装结构：optional、repeat、seq
- 语法层结构（如 DeclaratorList、Statement 等）一律保留，不被消除
- 所有规范化逻辑在代码内部硬编码，不依赖外部 TOML 配置

硬编码的通用常量（适用于任何编程语言）：
  - EXTRACT_PREFIXES: 需要提取为字符串值的 token 名前缀
  - EXTRACT_NAMES:    需要提取为字符串值的精确 token 名
  - ELIMINATE_TYPES:  需要消除的 parser 内部包装节点
  - CHILDREN_FIELD:   AST 子节点字段名
  - BODY_FIELD:       AST body 字段名
"""

from typing import Any, Optional
from core.define import Node

# ============================================================
# 通用规范化常量（硬编码，不依赖 TOML 配置）
# ============================================================

# 需要提取为字符串值的 token 名前缀（keyword.xxx → "xxx"）
EXTRACT_PREFIXES = ["keyword.", "symbol."]

# 需要提取为字符串值的精确 token 名
EXTRACT_NAMES = frozenset({
    "literal.number",
    "literal.string",
    "literal.bool_true",
    "literal.bool_false",
    "literal.none",
})

# 核心消除集合（只消除 parser 内部结构）
# optional  → 空值过滤
# repeat    → 零次或多次重复（展开为列表）
# seq       → 序列（展开为列表）
# 注意：语法层结构（如 DeclaratorList）不在这里，保留原样
ELIMINATE_TYPES = frozenset({"optional", "repeat", "seq"})

# AST 字段名约定（与 core/define.py 中的 Node 类对齐）
CHILDREN_FIELD = "sub_node"
BODY_FIELD = "body"


def normalize_ast(
    value: Any,
    layouts: dict | None = None,
) -> Any:
    """
    递归规范化 AST。

    核心消除集合（硬编码，不依赖配置文件）：
        optional, repeat, seq  ← 仅这些是 parser 内部包装结构
    注意：DeclaratorList 是语法层结构，坚决不消除。
    """
    return _normalize(value, layouts)


def _normalize(value, layouts=None):
    """递归实现"""

    # ---- 列表展平 ----
    if isinstance(value, list):
        result = []
        for item in value:
            normalized = _normalize(item, layouts)
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
    for prefix in EXTRACT_PREFIXES:
        if node.node_name.startswith(prefix):
            return getattr(node, "value", node.node_name)
    if node.node_name in EXTRACT_NAMES:
        return getattr(node, "value", node.node_name)

    # 2. 消除包装节点（仅限 optional / repeat / seq，不碰语法层结构）
    if node.node_name in ELIMINATE_TYPES:
        if node.node_name == "optional":
            if (
                not hasattr(node, CHILDREN_FIELD)
                or getattr(node, CHILDREN_FIELD) is None
            ):
                return None
            sublist = getattr(node, CHILDREN_FIELD)
            if not sublist:
                return None
            return _normalize(sublist[0], layouts)

        # repeat / seq → 展平子节点列表
        result = []
        if hasattr(node, CHILDREN_FIELD) and getattr(node, CHILDREN_FIELD) is not None:
            for child in getattr(node, CHILDREN_FIELD):
                normalized = _normalize(child, layouts)
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

    # 3. 普通节点（含语法层结构如 DeclaratorList）：递归处理所有属性
    CORE_ATTRS = frozenset({"node_name", "start", "end"})
    for attr_name in list(vars(node)):
        if attr_name in CORE_ATTRS or attr_name.startswith("_"):
            continue
        val = getattr(node, attr_name)
        normalized = _normalize(val, layouts)
        if normalized is None:
            try:
                delattr(node, attr_name)
            except AttributeError:
                pass
        elif normalized is not val:
            setattr(node, attr_name, normalized)

    # 4. body_role = "flatten" 处理（由渲染器布局配置驱动）
    children = None
    if hasattr(node, CHILDREN_FIELD):
        children = getattr(node, CHILDREN_FIELD)

    if layouts:
        layout = layouts.get(node.node_name, {})
        body_cfg = layout.get("body", {})
        role = (
            body_cfg.get("role")
            if isinstance(body_cfg, dict)
            else layout.get("body_role")
        )
        if role == "flatten":
            body = getattr(node, BODY_FIELD, None)
            if body is not None:
                if children is None:
                    children = []
                    setattr(node, CHILDREN_FIELD, children)
                if isinstance(body, list):
                    children.extend(body)
                elif isinstance(body, Node):
                    body_children = getattr(body, CHILDREN_FIELD, [])
                    if isinstance(body_children, list):
                        children.extend(body_children)
                    else:
                        children.append(body_children)
                # 移除旧的 body 引用
                new_children = [c for c in children if c is not body]
                if new_children:
                    setattr(node, CHILDREN_FIELD, new_children)
                elif hasattr(node, CHILDREN_FIELD):
                    delattr(node, CHILDREN_FIELD)
                try:
                    delattr(node, BODY_FIELD)
                except AttributeError:
                    pass

    # 5. 如果 children 为空列表，删除该属性
    if hasattr(node, CHILDREN_FIELD):
        children_val = getattr(node, CHILDREN_FIELD)
        if children_val is not None and len(children_val) == 0:
            delattr(node, CHILDREN_FIELD)

    return node
