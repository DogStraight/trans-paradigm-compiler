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
Doc: docs/language_walkthrough.md（normalizer：结构保留规范化）
"""

from typing import Any
from core.define import Node, BODY_FIELD, CHILDREN_FIELD
from core.token_protocol import KEYWORD_PREFIX, SYMBOL_PREFIX, LITERAL_PREFIX

# ── 通用规范化常量（硬编码，不依赖 TOML 配置）──

# 需要提取为字符串值的 token 名前缀（keyword.xxx → "xxx"）——token 叶子节点的
# 名字即 token 类型，前缀是引擎 token 协议（core/token_protocol）。literal.*
# 同样提取（literal.number → 值），不再列具体字面量名（A7：语言词法名不进引擎）。
EXTRACT_PREFIXES = [KEYWORD_PREFIX, SYMBOL_PREFIX, LITERAL_PREFIX]

# 核心消除集合（仅 parser 内部结构）
# optional  → filter None
# repeat    → zero-or-more (unfold to list)
# seq       → sequence (unfold to list)
# 注：语法层结构（如 DeclaratorList）原样保留
ELIMINATE_TYPES = frozenset({"optional", "repeat", "seq"})

# AST 字段名约定（与 core/define.py 的 Node 类对齐）
# CHILDREN_FIELD / BODY_FIELD 从 core.define 导入（单一事实源）


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


# 普通节点里不参与规范化的属性（结构元数据）
_CORE_ATTRS = frozenset({"node_name", "start", "end"})

# `_extract_token_value` 的"不是 token 叶子"哨兵（token 的值本身可能是 None）
_NO_EXTRACT = object()


def _normalize(value, layouts=None):
    """递归实现：按「列表 / 非节点 / token 叶子 / 包装节点 / 普通节点」分派。"""

    # ---- 列表展平 ----
    if isinstance(value, list):
        return _normalize_each(value, layouts)

    if not isinstance(value, Node):
        return value

    node = value

    # 1. 按名称前缀提取字面值（用于 token 节点归一化）
    extracted = _extract_token_value(node)
    if extracted is not _NO_EXTRACT:
        return extracted

    # 2. 消除包装节点（仅限 optional / repeat / seq，不碰语法层结构）
    if node.node_name in ELIMINATE_TYPES:
        if node.node_name == "optional":
            return _unwrap_optional(node, layouts)
        return _unwrap_container(node, layouts)

    # 3. 普通节点（含语法层结构如 DeclaratorList）：递归处理所有属性
    _normalize_attrs(node, layouts)

    # 4. body_role = "flatten" 处理（由渲染器布局配置驱动）
    children = getattr(node, CHILDREN_FIELD, None)
    if layouts and _body_role(layouts, node) == "flatten":
        _flatten_body_into_children(node, children)

    # 5. 如果 children 为空列表，删除该属性
    _drop_empty_children(node)
    return node


def _normalize_each(items, layouts) -> list:
    """逐个规范化并按需展平子列表（归一为 None 的项丢弃）。"""
    result = []
    for item in items:
        normalized = _normalize(item, layouts)
        if normalized is None:
            continue
        if isinstance(normalized, list):
            result.extend(normalized)
        else:
            result.append(normalized)
    return result


def _extract_token_value(node: Node):
    """token 叶子（`keyword.*` / `symbol.*` / `literal.*`）→ 其字面值。

    非 token 叶子返回 `_NO_EXTRACT`（用哨兵而不是 None：token 的值本身可能是 None）。
    """
    for prefix in EXTRACT_PREFIXES:
        if node.node_name.startswith(prefix):
            return getattr(node, "value", node.node_name)
    return _NO_EXTRACT


def _unwrap_optional(node: Node, layouts):
    """`optional` 包装：取首个子节点的规范化结果；无子节点 → None（丢弃该包装）。"""
    sublist = getattr(node, CHILDREN_FIELD, None)
    if not sublist:
        return None
    return _normalize(sublist[0], layouts)


def _unwrap_container(node: Node, layouts):
    """`repeat` / `seq` 包装：展平子节点 → 空为 None、单个取元素、多个为列表。"""
    children = getattr(node, CHILDREN_FIELD, None)
    if children is None:
        return None
    result = _normalize_each(children, layouts)
    if not result:
        return None
    if len(result) == 1:
        return result[0]
    return result


def _normalize_attrs(node: Node, layouts) -> None:
    """普通节点：递归规范化每个非核心属性（就地写回）。

    归一为 None 的属性**删除**（空属性不进规范 AST）；值未变的属性不动
    （`normalized is not val`）。
    """
    for attr_name in list(vars(node)):
        if attr_name in _CORE_ATTRS or attr_name.startswith("_"):
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


def _body_role(layouts: dict, node: Node):
    """该节点布局声明的 body role（`body.role`；旧式 `body_role` 兼容位）。"""
    layout = layouts.get(node.node_name, {})
    body_cfg = layout.get("body", {})
    if isinstance(body_cfg, dict):
        return body_cfg.get("role")
    return layout.get("body_role")


def _flatten_body_into_children(node: Node, children: list | None) -> None:
    """`body.role == "flatten"`：把 body 子节点并入 children，删旧 body 引用。

    body 为列表 → 直接并入；为单个节点 → 并入其 children（不是 Node.children
    形态则整节点并进）。最后按同一性（`is`）把 body 自身从 children 摘掉，
    children 空则删属性。
    """
    body = getattr(node, BODY_FIELD, None)
    if body is None:
        return
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


def _drop_empty_children(node: Node) -> None:
    """children 为空列表 → 删除该属性（空表无意义，规范 AST 不留空属性）。"""
    children_val = getattr(node, CHILDREN_FIELD, None)
    if children_val is not None and len(children_val) == 0:
        delattr(node, CHILDREN_FIELD)
