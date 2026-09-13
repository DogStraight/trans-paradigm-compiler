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
from typing import Any, Callable, ClassVar, TypeVar, overload
from core.define import Node
from analyzer.scope import Scope

# ── 全局注册表 ──

_plugin_registry: list[type["TransformPlugin"]] = []
# 限定名 → 类（插件身份面，ADR-0015 §1：插件实例化对象是一等单元，
# 需可寻址 → 管线配置按名引用）与注册序（缺省执行序）。
_plugin_index: dict[str, type["TransformPlugin"]] = {}
# 插件契约（ADR-0015 §3）：限定名 → {produces, requires}——**插件侧注册时声明**，
# 显式平铺列表（同语法 production 列表风格）。未声明 = 不参与校验（可选能力）。
_plugin_contracts: dict[str, dict[str, list[str]]] = {}


_T = TypeVar("_T", bound="TransformPlugin")


@overload
def register_plugin(
    cls: type[_T],
    *,
    name: str | None = None,
    produces: list[str] | None = None,
    requires: list[str] | None = None,
) -> type[_T]: ...


@overload
def register_plugin(
    cls: None = None,
    *,
    name: str | None = None,
    produces: list[str] | None = None,
    requires: list[str] | None = None,
) -> Callable[[type[_T]], type[_T]]: ...


def register_plugin(
    cls: type["TransformPlugin"] | None = None,
    *,
    name: str | None = None,
    produces: list[str] | None = None,
    requires: list[str] | None = None,
) -> Any:
    """装饰器：注册一个变换插件类（可带限定名 + 契约声明）。

    Usage:
        @register_plugin                        # 名 = 类名，无契约
        class MyPlugin(TransformPlugin): ...

        @register_plugin(name="typed_ports.bridge", requires=["scope"])
        class ComponentSlotPlugin(TransformPlugin): ...

    契约（produces/requires）= 显式平铺名列表（引擎只做机械核验，不懂语义）；
    **不含时点**——时点只在管线配置（`[pipeline.units.*]`）里编排（ADR-0015 §1）。
    重名 → 索引取**首个注册者**（同一插件文件被多路径 import 时类对象不同名同，
    是既有常态，不报错）；`_plugin_registry` 保留全部注册（不动现状执行序）。
    """

    def _register(klass: type["TransformPlugin"]) -> type["TransformPlugin"]:
        qname = name or klass.__name__
        # 索引：首胜（按名引用取注册序首个）；registry：照旧全注册
        _plugin_index.setdefault(qname, klass)
        _plugin_registry.append(klass)
        contract = {
            "produces": list(produces or []),
            "requires": list(requires or []),
        }
        if contract["produces"] or contract["requires"]:
            _plugin_contracts.setdefault(qname, contract)
        return klass

    if cls is not None:
        return _register(cls)
    return _register


def get_plugin_contracts() -> dict[str, dict[str, list[str]]]:
    """已注册插件的契约声明（限定名 → {produces, requires}），无声明者不在内。"""
    return {k: dict(v) for k, v in _plugin_contracts.items()}


def get_plugin_index() -> dict[str, type["TransformPlugin"]]:
    """已注册插件（限定名 → 类），供管线配置按名引用 + fail-fast 校验。"""
    return dict(_plugin_index)


def plugin_name_of(cls: type["TransformPlugin"]) -> str:
    """类 → 限定名（未登记的类回落类名）。"""
    for qname, k in _plugin_index.items():
        if k is cls:
            return qname
    return cls.__name__


class TransformPlugin(ABC):
    """AST 变换插件基类"""

    _transformer: "AstTransformer | None" = None

    @abstractmethod
    def process(self, ast: Node, root_scope: Scope) -> Node: ...

    @property
    def stats(self) -> dict[str, int]:
        """变换统计，子类可覆盖"""
        return {}

    def describe(self) -> dict:
        """插件自述中间产物 / 来源（可视化管道，ADR-0015 §2）。

        返回结构由插件自定（自由 dict）；引擎只做容器与落盘（收集进
        trace 条目的 `artifacts`），不解析内容——语言知识不进引擎。
        默认空 dict = 无自述（可选能力，见 ADR-0015 可选纪律设施）。
        """
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

    def describe_plugins(self) -> dict[str, dict]:
        """收集所有插件的自述（仅非空者），键 = 插件限定名。

        可视化管道：调度层把结果记进单元执行轨迹（trace 条目的
        `artifacts`），供 dump / 追踪中间产物与来源。
        """
        out: dict[str, dict] = {}
        for plugin in self._plugins:
            info = plugin.describe()
            if info:
                out[plugin_name_of(type(plugin))] = info
        return out


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


def _collect_subtree_comments(node: Any, acc_slots: dict) -> None:
    """递归收集节点子树的注释（_comment_slots 槽位）。

    替换语义下旧子树整体丢弃，其注释（可能挂在任意层级——如 `spi.slave
    spi_io // 注释` 的行尾注释挂在 instance_name 的 Identifier 子节点）
    全部迁移到替换产物，防注释随丢弃子树丢失。

    槽位值两形态（ADR-0013 阶段 A 后均存在）：
      - list（leading/inline/trailing）：直接扩展
      - dict（inline_after = {锚 token: [(注释, 源行号)]}）：按键合并
        （锚 keys 合并去重，entries 按 (text, line) 去重）
    """
    if isinstance(node, Node):
        slots = getattr(node, "_comment_slots", None)
        if slots:
            for k, v in slots.items():
                if isinstance(v, dict):
                    merged = acc_slots.setdefault(k, {})
                    for anchor, entries in v.items():
                        cur = merged.setdefault(anchor, [])
                        for e in entries:
                            if e not in cur:
                                cur.append(e)
                elif isinstance(v, list):
                    acc_slots.setdefault(k, []).extend(v)
                else:
                    acc_slots.setdefault(k, []).append(v)
        for k, v in list(vars(node).items()):
            if k.startswith("_"):
                continue
            _collect_subtree_comments(v, acc_slots)
    elif isinstance(node, list):
        for item in node:
            _collect_subtree_comments(item, acc_slots)
    elif isinstance(node, dict):
        for item in node.values():
            _collect_subtree_comments(item, acc_slots)


def migrate_comments(old_node: Any, new_node: Any) -> Any:
    """变换时注释迁移（注释节点模型步骤 3，P1.5）。

    新节点继承被替换节点**子树**的注释（_comment_slots 槽位）——1:1 与
    1:N 替换的通用通道：`impl ... => top; // 注释` 变换为 ModuleInst、
    `spi.slave spi_io // 注释` 展开为多个端口后，注释随结构走（渲染在
    替换产物上），不依赖锚点回插（变换路径普通注释锚点漂移的问题由此根治）。

    Returns: new_node（便于链式调用 `new.append(migrate_comments(c, result))`）。
    """
    if (
        not isinstance(old_node, Node)
        or not isinstance(new_node, Node)
        or new_node is old_node
    ):
        return new_node
    acc_slots: dict = {}
    _collect_subtree_comments(old_node, acc_slots)
    if not acc_slots:
        return new_node
    new_slots = getattr(new_node, "_comment_slots", None)
    if acc_slots:
        if new_slots is None:
            new_node.add_attr("_comment_slots", dict(acc_slots))
        else:
            for k, v in acc_slots.items():
                if k not in new_slots:
                    new_slots[k] = v
                elif isinstance(v, dict):
                    # inline_after 字典合并（锚 keys + entries 去重）
                    merged = new_slots[k]
                    for anchor, entries in v.items():
                        cur = merged.setdefault(anchor, [])
                        for e in entries:
                            if e not in cur:
                                cur.append(e)
                else:
                    new_slots[k] = new_slots[k] + v
    return new_node
