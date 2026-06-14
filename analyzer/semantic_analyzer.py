"""SemanticAnalyzer — AST 遍历构建符号表并解析标识符引用

输入: optimizer 优化后的 AST
输出:
    1. 带 _symbol_ref 链接的 AST（Identifier 节点附加 ._symbol_ref 属性）
    2. 符号表数据（Scope 树 + Symbol 列表）
"""

from typing import Dict, List, Optional, Any
from core.define import Node
from .scope import Scope, Symbol


class SemanticAnalyzer:
    """语义分析器：遍历 AST，注册声明，解析标识符引用"""

    def __init__(self, grammar_rules: Dict[str, Any]):
        self._rules = grammar_rules
        self._root_scope: Optional[Scope] = None
        self._current_scope: Optional[Scope] = None
        self._all_symbols: List[Symbol] = []

    def analyze(self, ast: Node) -> Node:
        """对 AST 进行语义分析，返回附带了 _symbol_ref 的 AST"""
        self._root_scope = Scope(name="<global>", kind="global")
        self._current_scope = self._root_scope
        self._all_symbols.clear()
        self._walk(ast)
        return ast

    @property
    def root_scope(self) -> Optional[Scope]:
        return self._root_scope

    @property
    def all_symbols(self) -> List[Symbol]:
        return self._all_symbols

    # ---- 递归遍历核心 ----

    def _walk(self, node: Any) -> None:
        if isinstance(node, Node):
            self._walk_node(node)
        elif isinstance(node, list):
            for item in node:
                self._walk(item)

    def _walk_node(self, node: Node) -> None:
        rule = self._rules.get(node.name)
        scope = self._current_scope
        assert scope is not None, "analyze() must be called before walking"

        # 1. 进入新作用域
        if rule and getattr(rule, "scope_open", False):
            name_attr = getattr(rule, "scope_name_attr", None)
            scope_name = (
                str(getattr(node, name_attr, node.name)) if name_attr else node.name
            )
            kind = getattr(rule, "scope_kind", "block")
            new_scope = Scope(name=scope_name, kind=kind, parent=scope)
            scope.children.append(new_scope)
            self._current_scope = new_scope
            scope = new_scope

        # 2. 声明符号
        if rule and hasattr(rule, "symbol_kind"):
            self._declare_from_node(node, rule, scope)

        # 3. 解析 Identifier 引用
        if node.name == "Identifier":
            self._resolve_identifier(node, scope)

        # 4. 递归子节点（通过统一的 iter_children 接口）
        for child in node.iter_children():
            self._walk(child)

        # 5. 退出作用域
        if rule and getattr(rule, "scope_open", False):
            self._current_scope = scope.parent
            assert self._current_scope is not None

    # ---- 符号声明 ----

    def _declare_from_node(self, node: Node, rule: dict, scope: Scope) -> None:
        kind: str = getattr(rule, "symbol_kind", "unknown")
        name_attr = getattr(rule, "symbol_name", None)

        if not name_attr:
            return

        names = self._extract_names(node, name_attr)
        for name in names:
            if name:
                sym = scope.declare(name, kind, node)
                self._all_symbols.append(sym)

    @staticmethod
    def _extract_names(node: Node, name_attr: str) -> list[str]:
        """从节点属性中提取符号名列表，支持列表属性（如 items）"""
        parts = name_attr.split(".")
        val: Any = node

        for p in parts:
            if isinstance(val, Node):
                val = getattr(val, p, None)
            elif isinstance(val, list):
                # 从列表每个元素提取属性
                results = []
                for item in val:
                    if isinstance(item, Node):
                        v = getattr(item, p, None)
                        name = SemanticAnalyzer._resolve_name_value(v)
                        if name:
                            results.append(name)
                return results
            else:
                return []

        if isinstance(val, list):
            # 最终值是列表（如 items），提取每个元素的 param_name
            return [
                n
                for item in val
                if isinstance(item, Node)
                for n in [
                    SemanticAnalyzer._resolve_name_value(
                        getattr(item, "param_name", None)
                    )
                ]
                if n
            ]
        name = SemanticAnalyzer._resolve_name_value(val)
        return [name] if name else []

    @staticmethod
    def _resolve_name_value(val: Any) -> Optional[str]:
        """将值解析为符号名字符串"""
        if val is None:
            return None
        if isinstance(val, Node):
            return getattr(val, "content", getattr(val, "value", None))
        if isinstance(val, str):
            return val
        return str(val) if val is not None else None

    # ---- 标识符解析 ----

    def _resolve_identifier(self, node: Node, scope: Scope) -> None:
        name = getattr(node, "content", None) or getattr(node, "name", None)
        if not name:
            return
        sym = scope.resolve(name)
        if sym:
            # 在 Identifier 节点上附加符号引用
            node.add_attr("_symbol_ref", sym)

    # ---- 子节点收集（已由 Node.iter_children() 替代）----
