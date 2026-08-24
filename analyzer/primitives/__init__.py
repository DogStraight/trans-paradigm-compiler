"""analyzer/primitives/ — primitive registry and built-in primitives.

Built-in analyzer primitives (scope, symbol, identifier, resolve) are
loaded here as regular imports — not through the component system.
Language-specific primitives are injected via components.
"""

from .registry import (
    register_primitive,
    get_primitive,
    has_primitive,
    list_primitives,
    register,
    AnalyzerPrimitive,
)

# Load built-in analyzer primitives (triggers @register decorators)
# _PRIMITIVE_MODULES 引用这些模块（表达"内置原语模块集合"），消除 pylance
# 对副作用 import 的"未存取"误报。
from . import _scope
from . import _symbol
from . import _identifier
from . import _resolve

_PRIMITIVE_MODULES = (_scope, _symbol, _identifier, _resolve)

__all__ = [
    "register_primitive",
    "get_primitive",
    "has_primitive",
    "list_primitives",
    "register",
    "AnalyzerPrimitive",
    "_PRIMITIVE_MODULES",
]
