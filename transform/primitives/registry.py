"""
registry.py — Transform 原语注册中心

与 analyzer/primitives/registry.py / preprocessor/primitives/registry.py 对称设计。
每个子系统都在 primitives/registry.py 中定义注册表 + @register 装饰器。
Doc: docs/language_walkthrough.md（变换原语注册机制）
"""

from __future__ import annotations
from typing import Callable, TYPE_CHECKING
from core.define import Node
from analyzer.scope import Scope

if TYPE_CHECKING:
    from ..config_driven import ConfigDrivenTransform


class _Skip:
    """标记值：跳过变换，不修改节点"""

    def __repr__(self):
        return "SKIP"


SKIP = _Skip()

TransformResult = Node | list[Node] | None | _Skip


class TransformContext:
    """变换上下文"""

    def __init__(
        self,
        rule_name: str = "",
        config: dict | None = None,
        tables: dict | None = None,
        extra: dict | None = None,
    ):
        self.rule_name = rule_name
        self.config = config or {}
        self.tables = tables or {}
        self.extra = extra or {}


# Primitive 签名：(engine, node, config, root_scope) → TransformResult
TransformPrimitive = Callable[
    ["ConfigDrivenTransform", Node, dict, Scope], TransformResult
]

# ── 注册中心 ──

_registry: dict[str, TransformPrimitive] = {}


def register_primitive(name: str, fn: TransformPrimitive) -> None:
    """注册一个变换原语。"""
    if name in _registry:
        raise ValueError(f"Transform primitive '{name}' 已注册")
    _registry[name] = fn


def get_primitive(name: str) -> TransformPrimitive | None:
    return _registry.get(name)


def list_primitives() -> list[str]:
    return list(_registry.keys())


# ── 装饰器 ──


def register(name: str) -> Callable:
    """装饰器：注册一个变换原语。

    Usage:
        @register("expand")
        def handle_expand(engine, node, config, root_scope):
            ...
    """

    def decorator(fn: TransformPrimitive) -> TransformPrimitive:
        register_primitive(name, fn)
        return fn

    return decorator
