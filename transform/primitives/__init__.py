"""transform/primitives — 变换引擎原语

提供配置驱动的 AST 变换原语，包括查表、遍历、节点创建/替换、模板解析。
"""

from .registry import (
    SKIP,
    TransformContext,
    register_primitive,
    get_primitive,
    list_primitives,
    register,
)
from .lookup import lookup
from .flow import foreach
from .node import emit, replace
from .template import resolve_template, resolve_attrs

__all__ = [
    "SKIP",
    "TransformContext",
    "register_primitive",
    "get_primitive",
    "list_primitives",
    "register",
    "lookup",
    "foreach",
    "emit",
    "replace",
    "resolve_template",
    "resolve_attrs",
]
