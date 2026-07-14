"""
registry.py — （旧位置，向下兼容）

原语注册中心已迁移到 transform/primitives/registry.py。
本文件保留为 re-export 入口，新增代码请使用新路径。
"""

from .primitives.registry import (
    _Skip, SKIP, TransformResult, TransformContext,
    TransformPrimitive,
    register_primitive, get_primitive, list_primitives,
    register,
)
