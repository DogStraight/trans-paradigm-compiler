"""SemanticAnalyzer — 原语驱动的语义分析器

职责：
    AST 遍历 + 原语分派管线。
    遍历 AST，对每个节点根据 TOML [RuleName.analyzer] 配置
    依次执行注册的分析器原语。

    原语管线顺序（由 _PRIMITIVE_ORDER 定义）：
        1. symbol_declare     — 在进入作用域前声明符号（注册到父作用域）
        2. scope_enter        — 进入新作用域
        3. identifier_resolve — 解析标识符引用
        4. scope_exit         — 退出作用域（递归子节点后执行）

设计原则：
    语言无关 — 所有原语不包含 Verilog 专用逻辑
    可组合 — 原语按需注册，TOML 配置决定哪些触发
    可扩展 — 自定义原语通过 register_primitive 注入，无需改此文件
"""

from typing import Dict, List, Optional, Any
from core.define import Node
from .scope import Scope, Symbol
from .primitives import (
    get_primitive,
    has_primitive,
    register_capture_hook,
)

# 重新导出 register_capture_hook（兼容现有导入）
# capture_hook 注册中心已移到 primitives/symbol.py

# ── 原语执行管线顺序 ──
# symbol_declare 在 scope_enter 之前：符号注册到父作用域
# identifier_resolve 在 scope_enter 之后：解析引用时可在新作用域中查找
# scope_exit 由 _walk_node 在递归后调度

_PRIMITIVE_ORDER = [
    "symbol_declare",      # 1. 先声明符号（注册到父作用域）
    "scope_enter",         # 2. 再进入新作用域
    "identifier_resolve",  # 3. 解析标识符引用
    "scope_exit",          # 4. 退出作用域（递归后执行，非此处调度）
]


class SemanticAnalyzer:
    """原语驱动的语义分析器

    遍历 AST，对每个节点根据 TOML [RuleName.analyzer] 配置
    依次执行注册的分析器原语。
    """

    def __init__(self, grammar_rules: Dict[str, Any]):
        self._rules = grammar_rules
        self._root_scope: Optional[Scope] = None
        self._current_scope: Optional[Scope] = None
        self._all_symbols: List[Symbol] = []
        self._errors: List[str] = []
        self._unresolved_refs: List[str] = []
        # 作用域定义名节点 ID 集合（跳过这些节点自身的 identifier_ref）
        self._scope_name_node_ids: set[int] = set()

    def analyze(self, ast: Node) -> Node:
        """对 AST 进行语义分析，返回带 _symbol_ref 的 AST（只读）"""
        self._root_scope = Scope(name="<global>", kind="global")
        self._current_scope = self._root_scope
        self._all_symbols.clear()
        self._errors.clear()
        self._scope_name_node_ids.clear()
        self._unresolved_refs.clear()
        self._walk(ast)
        return ast

    @property
    def has_errors(self) -> bool:
        return len(self._errors) > 0 or len(self._unresolved_refs) > 0

    @property
    def root_scope(self) -> Optional[Scope]:
        return self._root_scope

    @property
    def all_symbols(self) -> List[Symbol]:
        return self._all_symbols

    @property
    def errors(self) -> List[str]:
        return self._errors

    @property
    def unresolved_refs(self) -> List[str]:
        return self._unresolved_refs

    # ---- 递归遍历核心 ----

    def _walk(self, node: Any) -> None:
        """递归遍历 AST，对每个 Node 执行原语管线"""
        if isinstance(node, Node):
            self._walk_node(node)
        elif isinstance(node, list):
            for item in node:
                self._walk(item)

    def _walk_node(self, node: Node) -> None:
        """对单个节点执行原语管线

        管线顺序：
            1. symbol_declare  — 符号声明（在 scope_enter 前，注册到父作用域）
            2. scope_enter     — 进入新作用域
            3. identifier_resolve — 引用解析
            4. 递归子节点
            5. scope_exit      — 退出作用域
        """
        rule = self._rules.get(node.node_name)
        config = getattr(rule, "analyzer", {}) if rule else {}

        # 按预定顺序执行标准原语（scope_exit 除外，它在递归后执行）
        for prim_name in _PRIMITIVE_ORDER:
            if prim_name == "scope_exit":
                continue  # scope_exit 在递归后处理
            prim = get_primitive(prim_name)
            if prim is None:
                continue
            if _is_primitive_triggered(prim_name, config):
                prim(self, node, config)

        # 执行自定义原语（由 [RuleName.analyzer] primitives 列表声明）
        custom_primitives: list = config.get("primitives", [])
        if isinstance(custom_primitives, list):
            for prim_name in custom_primitives:
                if prim_name in _PRIMITIVE_ORDER:
                    continue  # 已在标准原语中处理过
                prim = get_primitive(prim_name)
                if prim is not None:
                    prim(self, node, config)

        # 递归子节点
        for child in node.iter_children():
            self._walk(child)

        # scope_exit：递归后退回父作用域
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
