"""
registry.py — DSL 原语动态注册中心

原语模块通过 @register(key) 装饰器自动注册到全局调度表，
无需手动修改 __init__.py 的 dispatch 列表。
Doc: docs/renderer_architecture.md（原语注册机制 @register）
"""

from typing import Callable

# 全局注册表：[(key, handler_func), ...]
# 按注册顺序排列，dispatch 时也按此顺序匹配
_PRIMITIVE_REGISTRY: list[tuple[str, Callable]] = []


def register(*keys: str) -> Callable:
    """装饰器：将原语处理函数注册到全局调度表

    Args:
        *keys: 该处理函数对应的 TOML 键名（如 "ref"、"join"）

    Usage:
        @register("ref")
        def eval_ref(expr, node, parent_layout, renderer):
            ...
    """
    def wrapper(handler: Callable) -> Callable:
        for key in keys:
            _PRIMITIVE_REGISTRY.append((key, handler))
        return handler

    return wrapper


def get_registry() -> list[tuple[str, Callable]]:
    """返回注册表快照"""
    return list(_PRIMITIVE_REGISTRY)
