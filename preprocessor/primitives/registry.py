"""
registry.py — 预处理器指令处理器注册中心

与 renderer/primitives/registry.py / analyzer/primitives/registry.py 对称设计。
每个子系统都在 primitives/registry.py 中定义注册表 + @register 装饰器。
"""

from typing import Any, Callable


# ── Handler 签名 ──────────────────────────────────
# context 是 handler 之间共享的运行时状态
DirectiveContext = dict[str, Any]
DirectiveHandler = Callable[[str, str, str, DirectiveContext], None]


# ── 注册表 ────────────────────────────────────────

_registry: dict[str, DirectiveHandler] = {}


def register_primitive(name: str, fn: DirectiveHandler) -> None:
    """显式注册一个指令处理器。"""
    _registry[name] = fn


def get_primitive(name: str) -> DirectiveHandler | None:
    return _registry.get(name)


def list_primitives() -> list[str]:
    return list(_registry.keys())


# ── 装饰器 ────────────────────────────────────────


def register(name: str) -> Callable[[DirectiveHandler], DirectiveHandler]:
    """装饰器：注册一个指令处理器。

    Usage:
        @register("define")
        def handle_define(stripped, prefix, name, ctx):
            ...
    """
    def decorator(func: DirectiveHandler) -> DirectiveHandler:
        register_primitive(name, func)
        return func
    return decorator
