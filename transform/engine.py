"""
engine.py — AstTransformer + TransformPlugin 基类 + 自动注册

接收规范化 AST + 符号表，依次执行所有已注册的变换插件。
插件通过 @register_plugin 装饰器自动注册，管线入口只需创建 AstTransformer()。

额外输出（多文件分发）：
  TransformPlugin 可调用 mark_extra(name, subtree) 将 AST 子树标记为额外文件，
  render 前调用 collect_extra_asts() 收集，统一渲染。
Doc: docs/language_walkthrough.md（变换引擎）
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


def migrate_comments(old_node: Any, new_node: Any) -> Any:
    """变换时注释迁移（注释节点模型步骤 3，P1.5）。

    新节点继承被替换节点的注释槽位（_comment_slots：leading/trailing/
    inline/inline_after）——1:1 替换的通用通道：`impl ... => top; // 注释`
    变换为 ModuleInst 后注释随结构走（渲染在实例行尾），不依赖锚点回插
    （变换路径普通注释锚点漂移的问题由此根治）。

    Returns: new_node（便于链式调用 `new.append(migrate_comments(c, result))`）。
    """
    if (
        not isinstance(old_node, Node)
        or not isinstance(new_node, Node)
        or new_node is old_node
    ):
        return new_node
    old_slots = getattr(old_node, "_comment_slots", None)
    new_slots = getattr(new_node, "_comment_slots", None)
    if old_slots:
        if new_slots is None:
            new_node.add_attr("_comment_slots", dict(old_slots))
        else:
            for k, v in old_slots.items():
                if k not in new_slots:
                    new_slots[k] = v
                else:
                    new_slots[k] = new_slots[k] + v
    # 旧 attachment 通道（行尾注释，ADR-0006 注释遍）同样迁移
    old_attached = getattr(old_node, "_attached_comments", None)
    if old_attached:
        new_attached = getattr(new_node, "_attached_comments", None)
        if new_attached is None:
            new_node.add_attr("_attached_comments", list(old_attached))
        else:
            new_attached.extend(old_attached)
    return new_node
