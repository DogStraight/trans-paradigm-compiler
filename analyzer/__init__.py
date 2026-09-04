"""analyzer — 语义分析框架（AST → 作用域/符号/诊断）。

Design principles:
    Language-agnostic — no language-specific logic in this directory
    Extensible — language-specific primitives injected via external modules
Doc: analyzer/semantic_checks.md（语义检查插槽）
"""

from .scope import Scope, Symbol, get_symbol_kinds
from .traversal import AnalysisTraversal
from .context import AnalysisContext
from .diagnostic import Diagnostic
from .primitives import register_primitive, get_primitive


__all__ = [
    "Scope",
    "Symbol",
    "get_symbol_kinds",
    "AnalysisTraversal",
    "AnalysisContext",
    "Diagnostic",
    "register_primitive",
    "get_primitive",
]
