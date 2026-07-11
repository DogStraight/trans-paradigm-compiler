"""analyzer/ — 语义分析框架

职责（5 模块）:
    context.py     — [1] 上下文承载：AnalysisContext（原语间数据总线）
    traversal.py   — [2] 遍历调度：AnalysisTraversal（AST 遍历 + 原语分派）
    scope.py       — [3] 符号表管理：Scope / Symbol
    diagnostic.py  — [4] 诊断聚合：Diagnostic（结构化错误信息）
    primitives/    — [5] 原子操作库：原语注册 + 内置原语 + 工具函数

设计原则：
    语言无关 — 所有代码不包含任何语言专用逻辑
    可扩展 — 语言专用原语通过外部模块注入，不在此目录内
"""

from .scope import Scope, Symbol, get_symbol_kinds
from .traversal import AnalysisTraversal
from .context import AnalysisContext
from .diagnostic import Diagnostic
from .primitives import register_capture_hook, register_primitive, get_primitive


__all__ = [
    "Scope",
    "Symbol",
    "get_symbol_kinds",
    "AnalysisTraversal",
    "AnalysisContext",
    "Diagnostic",
    "register_capture_hook",
    "register_primitive",
    "get_primitive",
]
