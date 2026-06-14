"""Renderer — AST + 布局规则驱动的代码生成器

只包含 DSL 原语（text/ref/join/group/line/indent/opt），
所有语言特定知识来自 TOML 布局规则。
"""

from .renderer import Renderer
from .normalizer import normalize_ast

__all__ = ["Renderer", "normalize_ast"]
