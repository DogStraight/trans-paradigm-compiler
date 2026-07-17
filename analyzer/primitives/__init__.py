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
from . import _scope  # noqa: F401
from . import _symbol  # noqa: F401
from . import _identifier  # noqa: F401
from . import _resolve  # noqa: F401

__all__ = [
    "register_primitive",
    "get_primitive",
    "has_primitive",
    "list_primitives",
    "register",
    "AnalyzerPrimitive",
]
