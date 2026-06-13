# /optimizer/ast_optimizer.py
"""
ast_optimizer.py - 规则式 AST 优化器（无叶子值自动提取版本）

设计说明：
- 每条优化“变换”是一个独立函数，专注于一种模式转换。
- 变换通过 @optimize 装饰器注册，但推荐使用显式顺序控制。
- 优化器递归遍历 AST，按顺序应用变换。
- 本版本移除了 extract_leaf_value，避免了保护节点维护成本。
"""

from typing import Any, List, Callable
from define import Node

# ---------- 优化变换注册机制 ----------
_OPTIMIZE_TRANSFORMS: List[Callable] = []


def optimize(func: Callable) -> Callable:
    _OPTIMIZE_TRANSFORMS.append(func)
    return func


def get_optimize_transforms() -> List[Callable]:
    return _OPTIMIZE_TRANSFORMS.copy()


# ---------- 递归应用器 ----------
def _apply_transforms_to_node(node: Any, transforms: List[Callable]) -> Any:
    if isinstance(node, Node):
        for attr_name, attr_value in node.__dict__.items():
            setattr(node, attr_name, _apply_transforms_to_node(attr_value, transforms))
    elif isinstance(node, list):
        return [_apply_transforms_to_node(item, transforms) for item in node]

    result = node
    for transform_func in transforms:
        result = transform_func(result)
    return result


def optimize_ast(ast: Any, transforms: List[Callable] | None = None) -> Any:
    if transforms is None:
        transforms = get_optimize_transforms()
    return _apply_transforms_to_node(ast, transforms)


# ========== 基础简化变换 ==========


@optimize
def flatten_optional(node: Any) -> Any:
    if isinstance(node, Node) and node.name == "optional":
        children = getattr(node, "child", [])
        if len(children) == 1:
            return children[0]
        if len(children) == 0:
            return []
    return node


@optimize
def extract_keyword_value(node: Any) -> Any:
    if isinstance(node, Node) and node.name.startswith("keyword."):
        value = getattr(node, "value", None)
        return value if value is not None else ""
    return node


@optimize
def extract_id_value(node: Any) -> Any:
    if isinstance(node, Node) and node.name == "id":
        value = getattr(node, "value", None)
        return value if value is not None else ""
    return node


@optimize
def flatten_repeat_sequence(node: Any) -> Any:
    if isinstance(node, Node) and node.name in ("repeat", "sequence"):
        children = getattr(node, "child", [])
        return [
            c
            for c in children
            if not (isinstance(c, Node) and c.name == "symbol.base.comma")
        ]
    return node


@optimize
def flatten_first_rest_list(node: Any) -> Any:
    if not isinstance(node, Node):
        return node

    first = getattr(node, "first", None)
    rest = getattr(node, "rest", None)
    if first is None and rest is None:
        return node

    def _to_flat_list(item):
        if item is None:
            return []
        if isinstance(item, list):
            result = []
            for sub in item:
                result.extend(_to_flat_list(sub))
            return result
        if isinstance(item, Node):
            if item.name == "symbol.base.comma":
                return []
            if item.name in ("symbol.extend.logic_or", "keyword.or"):
                return []
            if item.name in ("repeat", "sequence"):
                children = getattr(item, "child", [])
                return _to_flat_list(children)
            return [item]
        return [item]

    result = []
    if first is not None:
        result.extend(_to_flat_list(first))
    if rest is not None:
        result.extend(_to_flat_list(rest))
    return result if result else []


# @optimize 已禁用 — 由 CG 模板递归渲染
def range_to_string(node: Any) -> Any:
    if isinstance(node, Node) and node.name == "Range":
        msb = getattr(node, "msb", None)
        lsb = getattr(node, "lsb", None)
        if isinstance(msb, Node):
            msb = getattr(msb, "value", getattr(msb, "content", str(msb)))
        if isinstance(lsb, Node):
            lsb = getattr(lsb, "value", getattr(lsb, "content", str(lsb)))
        if msb is not None and lsb is not None:
            return f"{msb}:{lsb}"
    return node


# ========== 结构展平变换 ==========


@optimize
def flatten_root(node: Any) -> Any:
    if isinstance(node, Node) and node.name == "Root":
        children = getattr(node, "child", [])
        if not children:
            return []
        if len(children) == 1:
            return children[0]
        return children
    return node


@optimize
def flatten_block(node: Any) -> Any:
    if isinstance(node, Node) and node.name == "Block":
        children = getattr(node, "child", [])
        return children if isinstance(children, list) else []
    return node


# @optimize 已禁用 — BeginEnd 保留由模板渲染（用于 case item 内的 begin...end）
def flatten_begin_end(node: Any) -> Any:
    return node


@optimize
def normalize_else_chain(node: Any) -> Any:
    """
    统一 else_chain 的表示，递归展平嵌套的 ElseIf/ElseBranch 链。
    将 IfStatement 的 else_chain 转换为一个平坦的字典列表。
    """
    if not isinstance(node, Node):
        return node
    if node.name != "IfStatement":
        return node

    else_chain = getattr(node, "else_chain", None)
    if else_chain is None:
        return node

    def _flatten_body(body):
        # 展平 Block 节点为语句列表（BeginEnd 保留，由模板渲染）
        if isinstance(body, Node):
            if body.name == "Block":
                return getattr(body, "child", [])
        return body

    def _flatten_else_chain(chain):
        """递归展平 else_chain，返回字典列表"""
        result = []
        if chain is None:
            return result
        # 处理列表或元组
        if isinstance(chain, (list, tuple)):
            for item in chain:
                result.extend(_flatten_else_chain(item))
            return result
        # 处理单个 Node
        if isinstance(chain, Node):
            if chain.name == "ElseIf":
                cond = getattr(chain, "condition", None)
                stmt = getattr(chain, "then_stmt", None)
                branch_dict = {"condition": cond, "body": _flatten_body(stmt)}
                result.append(branch_dict)
                # 递归处理内部 else_chain（可能有 ElseBranch 或更多 ElseIf）
                inner_chain = getattr(chain, "else_chain", None)
                result.extend(_flatten_else_chain(inner_chain))
                return result
            elif chain.name == "ElseBranch":
                stmt = getattr(chain, "body", None)
                branch_dict = {"body": _flatten_body(stmt)}
                result.append(branch_dict)
                return result
            else:
                # 未知节点，保留原样
                result.append(chain)
                return result
        # 其他基本类型
        return [chain]

    normalized = _flatten_else_chain(else_chain)
    if not normalized:
        # 删除空 else_chain 属性
        if hasattr(node, "else_chain"):
            delattr(node, "else_chain")
    else:
        setattr(node, "else_chain", normalized)
    return node


# ========== 显式控制优化顺序（无 extract_leaf_value） ==========


def get_ordered_transforms() -> List[Callable]:
    return [
        flatten_optional,
        extract_keyword_value,
        extract_id_value,
        flatten_repeat_sequence,
        flatten_first_rest_list,
        flatten_root,
        flatten_block,
        flatten_begin_end,
        normalize_else_chain,
    ]


def optimize_ast_ordered(ast: Any) -> Any:
    return optimize_ast(ast, transforms=get_ordered_transforms())


# ---------- 示例 ----------
if __name__ == "__main__":
    print("推荐优化顺序:", [f.__name__ for f in get_ordered_transforms()])
