"""Preprocessor — TOML-driven Verilog macro expansion and reversal.

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse
Doc: docs/api.md（管线第一阶段：宏展开/反向映射；机制文档待补）
"""

from core.config_registry import _CONFIG_DECLARATIONS
from . import _expand, _reverse
from ._expand import scan_directives, expand_tokens, enumerate_conditions
from ._reverse import protect_and_reverse, restore_condition_blocks

__all__ = [
    "scan_directives",
    "expand_tokens",
    "enumerate_conditions",
    "protect_and_reverse",
    "restore_condition_blocks",
    "get_config_refs",
    "_expand",
    "_reverse",
]


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    prefix = __name__ + "."
    return {
        k: var
        for k, entries in _CONFIG_DECLARATIONS.items()
        for mod, var in entries
        if mod.startswith(prefix)
    }
