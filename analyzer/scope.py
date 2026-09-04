"""Scope (scope chain) and Symbol (declared identifier) types.

Doc: analyzer/semantic_checks.md（作用域/符号模型）
"""

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
    """符号：一个已声明的标识符

    name / kind / scope — 所有符号共有的核心元数据
    attrs — 由语法规则的 symbol_capture 驱动，存储语言相关属性（如 width、value、direction）
    decl_node — 内部引用，不序列化
    """

    def __init__(
        self,
        name: str,
        kind: str,
        decl_node: Node,
        scope: "Scope | None",
        attrs: dict | None = None,
    ):
        self.name = name
        self.kind = kind
        self.decl_node = decl_node
        self.scope = scope
        self.attrs = attrs or {}

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "kind": self.kind}
        if self.scope:
            d["scope"] = self.scope.name
            d["scope_kind"] = self.scope.kind
        # 输出所有由语法规则捕获的属性（如 width、value、direction 等）
        for k, v in self.attrs.items():
            if v is not None:
                d[k] = v
        return d


class Scope:
    """作用域

    allow_duplicate: 允许同名符号声明（合并保留首例不报错）——由语法规则
    [analyzer.scope] 配置声明（如 generate 各分支互斥、同名实例化合法）。
    语义由规则字段提供，Scope 只承载，不判断具体作用域种类。
    """

    def __init__(
        self,
        name: str,
        kind: str = "block",
        parent: "Scope | None" = None,
        allow_duplicate: bool = False,
    ):
        self.name = name
        self.kind = kind 
        self.parent = parent
        self.allow_duplicate = allow_duplicate
        self.symbols: dict[str, Symbol] = {}
        self.children: list["Scope"] = []

    def declare(
        self,
        name: str,
        kind: str,
        decl_node: Node,
        attrs: dict | None = None,
    ) -> Symbol:
        """在当前作用域声明一个符号"""
        sym = Symbol(
            name=name,
            kind=kind,
            decl_node=decl_node,
            scope=self,
            attrs=attrs,
        )
        self.symbols[name] = sym
        return sym

    def resolve(self, name: str) -> Symbol | None:
        """沿作用域链查找符号"""
        if name in self.symbols:
            return self.symbols[name]
        if self.parent is not None:
            return self.parent.resolve(name)
        return None

    def find_child_scope(self, name: str, kind: str | None = None) -> "Scope | None":
        """按名称（和可选种类）递归查找子作用域（DFS）

        Args:
            name: 作用域名称
            kind: 可选，限定作用域种类（如 "type"、"module"）
        Returns:
            匹配的子 Scope，未找到返回 None
        """
        for child in self.children:
            if child.name == name:
                if kind is None or child.kind == kind:
                    return child
            # 递归深入
            found = child.find_child_scope(name, kind)
            if found is not None:
                return found
        return None

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "kind": self.kind}
        if self.symbols:
            d["symbols"] = [s.to_dict() for s in self.symbols.values()]
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d
