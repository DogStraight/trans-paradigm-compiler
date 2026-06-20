"""
ImplicitDeclPlugin — 隐式声明插件（可选）

遍历 AST，为未解析的 Identifier 节点自动创建占位符号。
替代 SemanticAnalyzer 中内置的隐式声明逻辑，
将其拆为独立插件，按需启用。
"""

from core.define import Node
from analyzer.scope import Scope
from transform.post.ast_transformer import TransformPlugin


class ImplicitDeclPlugin(TransformPlugin):
    """为未解析的标识符自动创建隐式声明符号

    语义分析器不再内置此功能；启用此插件后，
    所有未绑定到声明的 Identifier 都会获得一个 implicit 类型的占位符号。
    """

    def __init__(
        self,
        implicit_kind: str = "implicit",
        identifier_node_name: str = "Identifier",
        content_attr: str = "content",
        name_attr: str = "name",
    ):
        self._implicit_kind = implicit_kind
        self._identifier_node_name = identifier_node_name
        self._content_attr = content_attr
        self._name_attr = name_attr

    def process(self, ast: Node, root_scope: Scope) -> Node:
        """遍历 AST，为缺失 _symbol_ref 的 Identifier 创建隐式符号"""
        self._walk(ast, root_scope)
        return ast

    def _walk(self, node: Node, root_scope: Scope) -> None:
        self._process_node(node, root_scope)

    def _process_node(self, node: Node, root_scope: Scope) -> None:
        # 如果是 Identifier 且没有 _symbol_ref，尝试解析或创建隐式符号
        if node.node_name == self._identifier_node_name:
            if not hasattr(node, "_symbol_ref"):
                name = getattr(node, self._content_attr, None) or getattr(
                    node, self._name_attr, None
                )
                if name:
                    # 先尝试从根作用域解析
                    sym = root_scope.resolve(name)
                    if sym is None:
                        # 在根作用域创建隐式符号
                        sym = root_scope.declare(
                            name=name,
                            kind=self._implicit_kind,
                            decl_node=node,
                            attrs={"implicit": True},
                        )
                    node.add_attr("_symbol_ref", sym)

        # 递归子节点
        for child in node.iter_children():
            self._walk(child, root_scope)
