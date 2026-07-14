"""
_directives.py — （旧位置，向下兼容）

指令处理器注册中心已迁移到 preprocessor/primitives/registry.py。
每个处理器分散到 primitives/define.py / undef.py / include.py。
本文件保留为 re-export 入口，新增代码请使用新路径。
"""

from .primitives.registry import (
    DirectiveContext,
    DirectiveHandler,
    register_primitive,
    get_primitive as get_handler,
    list_primitives as list_handlers,
    register as register_directive,
)
from .primitives.include import (
    resolve_source_dir,
    _resolve_path as resolve_include_path,
    _INCLUDE_RE,
    _INCLUDE_ANGLE_RE,
)
