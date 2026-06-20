"""SemanticAnalyzer — 精简的语义分析器基类

遍历 AST，管理作用域，注册显式声明的符号，解析标识符引用。
语义概念（节点名、属性名、默认值）使用代码内联默认值。
作用域/符号自声明：语法规则 TOML 中的 scope={}/symbol={} 自描述语义角色，
规则名即语义，无需外部配置文件。

高级服务（隐式声明、位宽计算、常量折叠等）作为可选插件
注入 transform/post 管线，按需启用。
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
        self._errors: List[str] = []
    # 语义概念（节点名、属性名、默认值）直接使用字面量，无需配置文件或映射表

    # 配置文件加载方法已移除（_semantic.toml / _name_symbol.toml 已删除）

    def analyze(self, ast: Node) -> Node:
        """对 AST 进行语义分析，返回带 _symbol_ref 的 AST（只读）"""
        self._root_scope = Scope(name="<global>", kind="global")
        self._current_scope = self._root_scope
        self._all_symbols.clear()
        self._errors.clear()
        self._scope_name_node_ids: set[int] = set()
        self._walk(ast)
        return ast

    @property
    def root_scope(self) -> Optional[Scope]:
        return self._root_scope

    @property
    def all_symbols(self) -> List[Symbol]:
        return self._all_symbols

    @property
    def errors(self) -> List[str]:
        return self._errors

    # ---- 递归遍历核心 ----

    def _walk(self, node: Any) -> None:
        if isinstance(node, Node):
            self._walk_node(node)
        elif isinstance(node, list):
            for item in node:
                self._walk(item)

    def _walk_node(self, node: Node) -> None:
        rule = self._rules.get(node.node_name)
        scope = self._current_scope
        assert scope is not None, "analyze() must be called before walking"

        # 1. 进入新作用域（规则自声明）
        scope_meta = getattr(rule, "scope", None) if rule else None
        if scope_meta:
            name_attr = scope_meta.get("name_attr")
            if name_attr:
                name_val = getattr(node, name_attr, None)
                if isinstance(name_val, Node):
                    scope_name = getattr(name_val, "content", node.node_name)
                    self._scope_name_node_ids.add(id(name_val))
                elif name_val is not None:
                    scope_name = str(name_val)
                else:
                    scope_name = node.node_name
            else:
                scope_name = node.node_name
            kind = scope_meta.get("kind", "block")
            new_scope = Scope(name=scope_name, kind=kind, parent=scope)
            scope.children.append(new_scope)
            self._current_scope = new_scope
            scope = new_scope

        # 2. 声明符号（规则自声明）
        sym_meta = getattr(rule, "symbol", None) if rule else None
        if sym_meta:
            self._declare_from_node(node, sym_meta, scope)

        # 3. 解析标识符引用（规则自声明）
        if rule and getattr(rule, "identifier_ref", False):
            self._resolve_identifier(node, scope)

        # 4. 递归子节点
        for child in node.iter_children():
            self._walk(child)

        # 5. 退出作用域
        if scope_meta:
            self._current_scope = scope.parent
            assert self._current_scope is not None

    # 常量求值（位宽计算、符号值折叠等）已移至 transform/post/plugins/ 可选插件

    # ---- 符号声明 ----

    def _declare_from_node(self, node: Node, sym_rule: dict, scope: Scope) -> None:
        kind: str = sym_rule.get("kind", "unknown")
        name_attr = sym_rule.get("name_attr")
        if not name_attr:
            return

        names = self._extract_names(node, name_attr)
        for name in names:
            if not name:
                continue

            if name in scope.symbols:
                self._errors.append(f"重复声明 '{name}' 在作用域 '{scope.name}'")
                continue

            sym = scope.declare(name=name, kind=kind, decl_node=node, attrs={})
            self._all_symbols.append(sym)

    # ---- 路径遍历（共享 _walk_path / _extract_names）----

    @staticmethod
    def _walk_path(node: Node, path: str) -> Any:
        """沿点号路径遍历节点属性，逐层 yield。

        遇到 list → 展开每个元素继续遍历；
        遇到 Node → getattr；
        其他类型 → 终止。
        """
        parts = path.split(".")
        stack: list = [(node, 0)]
        while stack:
            val, idx = stack.pop()
            if idx >= len(parts):
                yield val
                continue
            p = parts[idx]
            if isinstance(val, Node):
                child = getattr(val, p, None)
                if child is not None:
                    stack.append((child, idx + 1))
            elif isinstance(val, list):
                for item in reversed(val):
                    stack.append((item, idx))
            else:
                return

    def _extract_names(self, node: Node, name_attr: str) -> list[str]:
        """从节点属性中提取符号名列表，支持列表属性（如 items）"""
        names: list[str] = []
        for val in SemanticAnalyzer._walk_path(node, name_attr):
            name = self._resolve_name_value(val)
            if name:
                names.append(name)
        if not names and isinstance(
            val := getattr(node, name_attr.split(".")[0], None), list
        ):
            # 兜底：尾部是列表，尝试从各元素提取名称
            fallback_attrs = ["param_name", "name"]
            for item in val:
                if isinstance(item, Node):
                    for attr_name in fallback_attrs:
                        n = getattr(item, attr_name, None)
                        if n:
                            name = self._resolve_name_value(n)
                            if name:
                                names.append(name)
                                break
        return names

    def _resolve_name_value(self, val: Any) -> Optional[str]:
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
        # 跳过作用域定义名自身的 Identifier（如模块名、函数名）
        if id(node) in self._scope_name_node_ids:
            return
        name = getattr(node, "content", None) or getattr(node, "name", None)
        if not name:
            return
        sym = scope.resolve(name)
        if sym is not None:
            node.add_attr("_symbol_ref", sym)
