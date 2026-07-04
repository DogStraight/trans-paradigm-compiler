"""registry.py — Transform 原语注册中心"""

from __future__ import annotations
from typing import Callable, Optional, TYPE_CHECKING
from core.define import Node
from analyzer.scope import Scope

if TYPE_CHECKING:
    from .core import ConfigDrivenTransform


class _Skip:
    """标记值：跳过变换，不修改节点"""

    def __repr__(self):
        return "SKIP"


SKIP = _Skip()

TransformResult = Node | list[Node] | None | _Skip


class TransformContext:
    """变换上下文（保留兼容，custom handler 用）"""

    def __init__(
        self,
        rule_name: str = "",
        config: Optional[dict] = None,
        tables: Optional[dict] = None,
        extra: Optional[dict] = None,
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

_primitive_registry: dict[str, TransformPrimitive] = {}


def register_primitive(name: str, fn: TransformPrimitive) -> None:
    """直接注册一个变换原语。

    内置原语在 engine.py 中注册，扩展原语在 __init__.py 或自定义模块中注册。
    TOML 中 kind = "xxx" 直接索引此注册表。
    """
    if name in _primitive_registry:
        raise ValueError(f"Transform primitive '{name}' 已注册")
    _primitive_registry[name] = fn


def get_primitive(name: str) -> Optional[TransformPrimitive]:
    """按名称获取已注册的原语"""
    return _primitive_registry.get(name)


# ── 向下兼容 ──
get_handler = get_primitive
