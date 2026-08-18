"""registry.py — analyzer primitive registry.

Symmetric design to transform/post/engine/registry.py but separate concerns.
Analyzer primitives handle semantic analysis during AST traversal
(scope, symbols, reference resolution).
Transform primitives handle post-phase AST modification
(expansion, replacement, deletion).

Registered primitives are injected into SemanticAnalyzer._walk_node pipeline,
executed in the order declared in TOML [RuleName.analyzer] configuration.
"""

from typing import Callable
from core.define import Node


# ── Primitive signature ──
#
# AnalyzerPrimitive = Callable[
#     analyzer: SemanticAnalyzer,    # Analyzer instance (holds scope/errors)
#     node: Node,                    # Current AST node
#     config: dict,                  # Analyzer config dictionary for this rule
# ] -> None
#
# 原语通过副作用修改分析器内部状态（scope、symbols、errors）

AnalyzerPrimitive = Callable[..., None]

# ── Primitive registry ──

_primitives: dict[str, AnalyzerPrimitive] = {}


def register_primitive(name: str, fn: AnalyzerPrimitive) -> None:
    """Register an analyzer primitive.

    Args:
        name: Primitive name, referenced in TOML configuration.
        fn: Primitive function, signature per AnalyzerPrimitive.
    """
    if name in _primitives:
        raise ValueError(f"Analyzer primitive '{name}' 已注册")
    _primitives[name] = fn


def get_primitive(name: str) -> AnalyzerPrimitive | None:
    """Get a registered primitive by name."""
    return _primitives.get(name)


def has_primitive(name: str) -> bool:
    """Check if a primitive is registered."""
    return name in _primitives


def list_primitives() -> list[str]:
    """列出所有已注册的原语名称"""
    return sorted(_primitives.keys())


# ── 装饰器 ──


def register(name: str) -> Callable:
    """装饰器：注册一个分析器原语。

    与 renderer/primitives/registry.py / transform/primitives/registry.py 统一签名。

    Usage:
        @register("scope_enter")
        def scope_enter(analyzer, node, config):
            ...
    """
    def decorator(fn: AnalyzerPrimitive) -> AnalyzerPrimitive:
        register_primitive(name, fn)
        return fn
    return decorator
