"""
AstTransformer — 后阶段 AST 变换管线

接收规范化 AST + 符号表，依次执行注册的变换插件。
每个插件实现 TransformPlugin 接口，可独立启用/禁用。
用法:
    transformer = AstTransformer()
    transformer.register(MyPlugin())
    ast = transformer.transform(ast, root_scope)
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from core.define import Node
from analyzer.scope import Scope


class TransformPlugin(ABC):
    """AST 变换插件基类

    子类只需实现 process() 方法，接收规范化 AST 和根作用域，
    返回（可能修改后的）AST。
    """

    @abstractmethod
    def process(self, ast: Node, root_scope: Scope) -> Node:
        """处理 AST，返回变换后的 AST"""
        ...


class AstTransformer:
    """后阶段变换管线

    依次执行所有已注册的插件，每个插件的输出作为下一个的输入。
    默认不含任何插件——所有高级服务均为可选注入。
    """

    def __init__(self, plugins: Optional[List[TransformPlugin]] = None):
        self._plugins: List[TransformPlugin] = list(plugins) if plugins else []

    def register(self, plugin: TransformPlugin) -> None:
        """注册一个变换插件"""
        self._plugins.append(plugin)

    @property
    def plugins(self) -> List[TransformPlugin]:
        return list(self._plugins)

    def transform(self, ast: Node, root_scope: Scope) -> Node:
        """对 AST 执行所有注册的变换"""
        for plugin in self._plugins:
            ast = plugin.process(ast, root_scope)
        return ast
