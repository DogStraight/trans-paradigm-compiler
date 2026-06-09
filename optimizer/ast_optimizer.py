"""
ast_optimizer.py - 规则式 AST 优化器（可扩展样本）

设计说明：
- 每条优化“变换”（transform）是一个独立函数，专注于一种模式转换。
- 变换通过 @optimize 装饰器注册到全局注册表。
- 优化器递归遍历 AST，按顺序应用所有注册的变换（或指定的变换列表）。
- 变换名称、注册表变量均包含 "optimize"/"opt" 前缀，与语法规则/模板规则区分。
"""

from typing import Any, List, Callable
from define import Node  # 假设 AST 节点基类

# ---------- 优化变换注册机制 ----------
_OPTIMIZE_TRANSFORMS: List[Callable] = []  # 存储已注册的变换函数（顺序 = 注册顺序）


def optimize(func: Callable) -> Callable:
    """
    装饰器：将一个函数注册为 AST 优化变换。
    变换函数签名：def transform_name(node: Any) -> Any
    - 输入：任意类型的节点（Node、列表、基本类型）
    - 输出：转换后的节点（类型可能改变）
    注意：变换只负责自己的模式转换，不应递归处理子节点（由优化器统一递归）。
    """
    _OPTIMIZE_TRANSFORMS.append(func)
    return func


def get_optimize_transforms() -> List[Callable]:
    """返回所有已注册的优化变换（按注册顺序）"""
    return _OPTIMIZE_TRANSFORMS.copy()


# ---------- 递归应用器 ----------
def _apply_transforms_to_node(node: Any, transforms: List[Callable]) -> Any:
    """
    对单个节点应用变换列表（后序遍历：先子后父）。
    返回转换后的节点。
    """
    # 1. 先递归处理子节点（如果是容器）
    if isinstance(node, Node):
        for attr_name, attr_value in node.__dict__.items():
            setattr(node, attr_name, _apply_transforms_to_node(attr_value, transforms))
    elif isinstance(node, list):
        return [_apply_transforms_to_node(item, transforms) for item in node]
    # 基本类型（str/int/None）无需递归

    # 2. 依次应用所有变换（每个变换都可能改变节点）
    result = node
    for transform_func in transforms:
        result = transform_func(result)
    return result


def optimize_ast(ast: Any, transforms: List[Callable]) -> Any:
    """
    对外接口：优化 AST。
    :param ast: 原始 AST（Node 树）
    :param transforms: 可选，指定变换列表（默认使用所有已注册变换）
    :return: 优化后的 AST
    """
    if transforms is None:
        transforms = get_optimize_transforms()
    return _apply_transforms_to_node(ast, transforms)


# ---------- 示例优化变换（可直接使用或作为模板） ----------
@optimize
def flatten_optional(node: Any) -> Any:
    """
    变换1：展平 optional 节点。
    AST 中 optional 结构：Node(name='optional', child=[实际节点])
    优化后：直接返回 child[0]（若有），去除包装层。
    """
    if isinstance(node, Node) and node.name == "optional":
        children = getattr(node, "child", [])
        if len(children) == 1:
            return children[0]
    return node


@optimize
def extract_keyword_value(node: Any) -> Any:
    """
    变换2：提取 keyword.* 节点的 value。
    例如：Node(name='keyword.input', value='input') -> 'input'
    """
    if isinstance(node, Node) and node.name.startswith("keyword."):
        value = getattr(node, "value", None)
        return value if value is not None else ""
    return node


@optimize
def extract_id_value(node: Any) -> Any:
    """
    变换3：提取 id 节点的 value。
    例如：Node(name='id', value='clk') -> 'clk'
    """
    if isinstance(node, Node) and node.name == "id":
        value = getattr(node, "value", None)
        return value if value is not None else ""
    return node


@optimize
def range_to_string(node: Any) -> Any:
    """
    变换4：将 Range 节点转换为 "msb:lsb" 字符串。
    自动提取 Number/Identifier 节点的 value/content。
    """
    if isinstance(node, Node) and node.name == "Range":
        msb = getattr(node, "msb", None)
        lsb = getattr(node, "lsb", None)
        # 如果 msb/lsb 是 Node，提取其值
        if isinstance(msb, Node):
            msb = getattr(msb, "value", getattr(msb, "content", str(msb)))
        if isinstance(lsb, Node):
            lsb = getattr(lsb, "value", getattr(lsb, "content", str(lsb)))
        if msb is not None and lsb is not None:
            return f"{msb}:{lsb}"
    return node


@optimize
def flatten_repeat_sequence(node: Any) -> Any:
    """
    变换5：展平 repeat / sequence 节点。
    repeat 结构：Node(name='repeat', child=[item1, item2, ...])
    优化后：直接返回 child 列表，去掉包装节点。
    """
    if isinstance(node, Node) and node.name in ("repeat", "sequence"):
        children = getattr(node, "child", [])
        return children
    return node


# ---------- 组合与调试示例 ----------
if __name__ == "__main__":
    print("已注册优化变换:", [f.__name__ for f in get_optimize_transforms()])

    # 可以只应用部分变换（而不是全部）
    custom_transforms = [flatten_optional, extract_id_value]
    # optimized_ast = optimize_ast(original_ast, transforms=custom_transforms)

    # 调试技巧：临时包装变换函数打印变化
    def debug_transform(transform_func):
        def wrapper(node):
            old_repr = repr(node)[:80]
            result = transform_func(node)
            new_repr = repr(result)[:80]
            if old_repr != new_repr:
                print(f"[{transform_func.__name__}] {old_repr} -> {new_repr}")
            return result

        return wrapper

    # 使用调试包装（注意：这不会影响原始注册，仅用于局部测试）
    # debugged = debug_transform(flatten_optional)
    # test_result = debugged(some_node)
