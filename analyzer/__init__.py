"""analyzer/ — semantic analysis framework

Modules (5):
    context.py     — AnalysisContext: data bus between primitives
    traversal.py   — AnalysisTraversal: AST walk + primitive dispatch
    scope.py       — Scope / Symbol: scope chain + symbol table
    diagnostic.py  — Diagnostic: structured diagnostics
    primitives/    — primitive registry and built-in primitives

Design principles:
    Language-agnostic — no language-specific logic in this directory
    Extensible — language-specific primitives injected via external modules
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
