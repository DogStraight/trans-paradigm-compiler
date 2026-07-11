"""AnalysisTraversal — 原语驱动的 AST 遍历调度

职责（对应分析器 5 模块之一：遍历调度）：
    遍历 AST，对每个节点根据 TOML [RuleName.analyzer] 配置
    依次执行注册的分析器原语。

文件结构中对应的职责模块：
    context.py        — [1] 上下文承载
    traversal.py    — [2] 遍历调度
    scope.py          — [3] 符号表管理
    diagnostic.py     — [4] 诊断聚合
    primitives/       — [5] 原子操作库

设计原则：
    语言无关 — 所有原语不包含 Verilog 专用逻辑
    可组合 — 原语按需注册，TOML 配置决定哪些触发
    可扩展 — 语言专用原语通过外部模块注入
"""

from typing import Dict, List, Optional, Any
from core.define import Node
from .scope import Scope, Symbol
from .context import AnalysisContext
from .diagnostic import Diagnostic
from .primitives import (
    get_primitive,
)

# ── 原语执行管线顺序 ──

_PRIMITIVE_ORDER = [
    "symbol_declare",      # 1. 先声明符号（注册到父作用域）
    "scope_enter",         # 2. 再进入新作用域
    "identifier_resolve",  # 3. 解析标识符引用
    "scope_exit",          # 4. 退出作用域（递归后执行）
]


class AnalysisTraversal:
    """原语驱动的语义分析管线

    遍历 AST，对每个节点根据 TOML [RuleName.analyzer] 配置
    依次执行注册的分析器原语。
    """

    def __init__(self, grammar_rules: Dict[str, Any]):
        self._rules = grammar_rules
        self._root_scope: Optional[Scope] = None
        self._current_scope: Optional[Scope] = None
        self._all_symbols: List[Symbol] = []
        self._context = AnalysisContext()
        # 作用域定义名节点 ID 集合
        self._scope_name_node_ids: set[int] = set()

    def analyze(self, ast: Node) -> Node:
        """对 AST 进行语义分析，返回带 _symbol_ref 的 AST"""
        self._root_scope = Scope(name="<global>", kind="global")
        self._current_scope = self._root_scope
        self._all_symbols.clear()
        self._context = AnalysisContext(root_scope=self._root_scope)
        self._scope_name_node_ids.clear()
        self._walk(ast)
        return ast

    @property
    def has_errors(self) -> bool:
        return len(self._context.diagnostics) > 0

    @property
    def root_scope(self) -> Optional[Scope]:
        return self._root_scope

    @property
    def all_symbols(self) -> List[Symbol]:
        return self._all_symbols

    @property
    def diagnostics(self) -> List[Diagnostic]:
        return self._context.diagnostics

    # ---- 递归遍历核心 ----

    def _walk(self, node: Any) -> None:
        if isinstance(node, Node):
            self._walk_node(node)
        elif isinstance(node, list):
            for item in node:
                self._walk(item)

    def _walk_node(self, node: Node) -> None:
        rule = self._rules.get(node.node_name)
        config = getattr(rule, "analyzer", {}) if rule else {}
        self._context.node = node
        self._context.config = config

        # 标准原语
        for prim_name in _PRIMITIVE_ORDER:
            if prim_name == "scope_exit":
                continue
            prim = get_primitive(prim_name)
            if prim is None:
                continue
            if _is_primitive_triggered(prim_name, config):
                prim(self, node, config)

        # 自定义原语
        custom_primitives: list = config.get("primitives", [])
        if isinstance(custom_primitives, list):
            for prim_name in custom_primitives:
                if prim_name in _PRIMITIVE_ORDER:
                    continue
                prim = get_primitive(prim_name)
                if prim is not None:
                    prim(self, node, config)

        # 递归子节点
        for child in node.iter_children():
            self._walk(child)

        # scope_exit
        scope_exit_prim = get_primitive("scope_exit")
        if scope_exit_prim is not None:
            if _is_primitive_triggered("scope_exit", config):
                scope_exit_prim(self, node, config)


# ============================================================
# 辅助函数
# ============================================================


def _is_primitive_triggered(prim_name: str, config: dict) -> bool:
    """判断指定原语是否应被当前配置触发

    原语与 TOML 配置字段的映射关系：
        symbol_declare     → config.symbol 存在
        scope_enter        → config.scope 存在
        scope_exit         → config.scope 存在
        identifier_resolve → config.identifier_ref 为真
    """
    if not config:
        return False

    if prim_name in ("symbol_declare",):
        return "symbol" in config
    if prim_name in ("scope_enter", "scope_exit"):
        return "scope" in config
    if prim_name == "identifier_resolve":
        return bool(config.get("identifier_ref", False))

    # 未知原语：由 TOML 中的 primitives 列表控制（未来扩展）
    primitives_list = config.get("primitives", [])
    if isinstance(primitives_list, list):
        return prim_name in primitives_list
    return False
