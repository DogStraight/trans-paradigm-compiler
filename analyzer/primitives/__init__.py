"""analyzer/primitives/ — 原语注册中心

原语实现在各组件目录（_components/*/）中，通过 @register 注册到此。
本目录只保留注册机制和通用工具函数。
"""

from .registry import (
    register_primitive,
    get_primitive,
    has_primitive,
    list_primitives,
    register,
    AnalyzerPrimitive,
)

__all__ = [
    "register_primitive",
    "get_primitive",
    "has_primitive",
    "list_primitives",
    "register",
    "AnalyzerPrimitive",
]
