"""Renderer — AST + 布局规则驱动的代码生成器（AST → 文本）。

只包含 DSL 原语（text/ref/join/group/line/indent/opt/align/fill/
line_suffix/intent 等），所有语言特定知识来自 TOML 布局规则。
Doc: docs/renderer_architecture.md（渲染器工作机制与现状：双世界 + Doc IR + 原语表）
"""

from .renderer import Renderer
from transform.normalizer import normalize_ast

__all__ = ["Renderer", "normalize_ast", "get_config_refs"]


from core.config_registry import _CONFIG_DECLARATIONS


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    prefix = __name__ + "."
    return {k: var for k, entries in _CONFIG_DECLARATIONS.items() for mod, var in entries if mod.startswith(prefix)}
