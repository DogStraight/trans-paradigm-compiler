"""
pipeline.py — AstTransformer + TransformPlugin 基类 + 自动注册

接收规范化 AST + 符号表，依次执行所有已注册的变换插件。
插件通过 @register_plugin 装饰器自动注册，管线入口只需创建 AstTransformer()。

额外输出（多文件分发）：
  TransformPlugin 可调用 mark_extra(name, subtree) 将 AST 子树标记为额外文件，
  render 前调用 collect_extra_asts() 收集，统一渲染。
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar
from core.define import Node
from analyzer.scope import Scope

# ── 全局注册表 ──

_plugin_registry: list[type["TransformPlugin"]] = []


def register_plugin(cls: type["TransformPlugin"]) -> type["TransformPlugin"]:
    """装饰器：注册一个变换插件类。

    Usage:
        @register_plugin
        class MyPlugin(TransformPlugin):
            def process(self, ast, root_scope): ...
    """
    _plugin_registry.append(cls)
    return cls


class TransformPlugin(ABC):
    """AST 变换插件基类"""

    _transformer: "AstTransformer | None" = None

    @abstractmethod
    def process(self, ast: Node, root_scope: Scope) -> Node: ...

    @property
    def stats(self) -> dict[str, int]:
        """变换统计，子类可覆盖"""
        return {}


class AstTransformer:
    """后阶段变换管线，依次执行所有已注册的插件"""

    _shared_ctx: ClassVar[dict[str, Any]] = {}

    def __init__(self, plugins: list[TransformPlugin] | None = None):
        if plugins is not None:
            self._plugins = list(plugins)
        else:
            # 从全局注册表自动实例化所有插件
            self._plugins = [cls() for cls in _plugin_registry]

    @classmethod
    def set_shared(cls, key: str, value: Any) -> None:
        """设置共享上下文（如 rules、mapping_cfg），插件在 __init__ 中按需取用。"""
        cls._shared_ctx[key] = value

    @classmethod
    def get_shared(cls) -> dict[str, Any]:
        """获取共享上下文字典。"""
        return cls._shared_ctx

    def register(self, plugin: TransformPlugin) -> None:
        self._plugins.append(plugin)

    @property
    def plugins(self) -> list[TransformPlugin]:
        return list(self._plugins)

    def transform(self, ast: Node, root_scope: Scope) -> Node:
        for plugin in self._plugins:
            plugin._transformer = self
            ast = plugin.process(ast, root_scope)
        return ast


# ── 额外 AST 输出（多文件分发）──

_EXTRA_ASTS_KEY = "_remapper_extra_asts"


def mark_extra(name: str, subtree: Node) -> None:
    """TransformPlugin 调用此函数将节点标记为额外文件输出。

    Args:
        name: 输出文件名（不含扩展名）
        subtree: 待渲染为独立文件的 AST 子树
    """
    ctx = AstTransformer.get_shared()
    if _EXTRA_ASTS_KEY not in ctx:
        ctx[_EXTRA_ASTS_KEY] = []
    ctx[_EXTRA_ASTS_KEY].append((name, subtree))


def collect_extra_asts() -> list[tuple[str, Node]]:
    """render 前调用：收集所有插件标记的额外输出。"""
    ctx = AstTransformer.get_shared()
    return ctx.pop(_EXTRA_ASTS_KEY, [])
