"""Scope 作用域与 Symbol 符号表"""

from typing import Optional, Dict, List
from core.define import Node


def get_symbol_kinds(rules: dict) -> frozenset[str]:
    """从语法规则配置中动态提取所有已知符号类别"""
    kinds: set[str] = set()
    for _, rule in rules.items():
        kind = (
            getattr(rule, "symbol_kind", None) if hasattr(rule, "symbol_kind") else None
        )
        if isinstance(kind, str):
            kinds.add(kind)
        elif isinstance(rule, dict):
            kind = rule.get("symbol_kind")
            if isinstance(kind, str):
                kinds.add(kind)
    return frozenset(kinds)


class Symbol:
    """符号：一个已声明的标识符"""

    def __init__(
        self,
        name: str,
        kind: str,
        decl_node: Node,
        scope: "Scope",
        width: Optional[int] = None,
    ):
        self.name = name
        self.kind = kind
        self.decl_node = decl_node
        self.scope = scope
        self.width = width

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "scope": self.scope.name if self.scope else None,
            "scope_kind": self.scope.kind if self.scope else None,
        }


class Scope:
    """作用域"""

    def __init__(
        self,
        name: str,
        kind: str = "block",
        parent: Optional["Scope"] = None,
    ):
        self.name = name
        self.kind = kind  # module / generate / function / task / block / for
        self.parent = parent
        self.symbols: Dict[str, Symbol] = {}
        self.children: List["Scope"] = []

    def declare(self, name: str, kind: str, decl_node: Node) -> Symbol:
        """在当前作用域声明一个符号"""
        sym = Symbol(name=name, kind=kind, decl_node=decl_node, scope=self)
        self.symbols[name] = sym
        return sym

    def resolve(self, name: str) -> Optional[Symbol]:
        """沿作用域链查找符号"""
        if name in self.symbols:
            return self.symbols[name]
        if self.parent is not None:
            return self.parent.resolve(name)
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "symbols": [s.to_dict() for s in self.symbols.values()],
            "children": [c.to_dict() for c in self.children],
        }
