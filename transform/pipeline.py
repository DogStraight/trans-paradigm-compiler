"""
pipeline.py — AstTransformer + TransformPlugin 基类

接收规范化 AST + 符号表，依次执行注册的变换插件。
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from core.define import Node
from analyzer.scope import Scope


class TransformPlugin(ABC):
    """AST 变换插件基类"""

    _transformer: Optional["AstTransformer"] = None

    @abstractmethod
    def process(self, ast: Node, root_scope: Scope) -> Node:
        ...

    @property
    def stats(self) -> dict[str, int]:
        """变换统计，子类可覆盖"""
        return {}


class AstTransformer:
    """后阶段变换管线，依次执行所有已注册的插件"""

    def __init__(self, plugins: Optional[List[TransformPlugin]] = None):
        self._plugins: List[TransformPlugin] = list(plugins) if plugins else []

    def register(self, plugin: TransformPlugin) -> None:
        self._plugins.append(plugin)

    @property
    def plugins(self) -> List[TransformPlugin]:
        return list(self._plugins)

    def transform(self, ast: Node, root_scope: Scope) -> Node:
        for plugin in self._plugins:
            plugin._transformer = self
            ast = plugin.process(ast, root_scope)
        return ast
