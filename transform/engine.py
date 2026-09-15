"""
engine.py — AstTransformer + TransformPlugin 基类 + 自动注册

接收规范化 AST + 符号表，依次执行所有已注册的变换插件。
插件通过 @register_plugin 装饰器自动注册，管线入口只需创建 AstTransformer()。

额外输出（多文件分发）：
  TransformPlugin 可调用 mark_extra(name, subtree) 将 AST 子树标记为额外文件，
  render 前调用 collect_extra_asts() 收集，统一渲染。
Doc: docs/language_walkthrough.md（变换引擎）
"""

import sys
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, TypeVar, overload
from core.define import Node
from analyzer.scope import Scope

# ── 全局注册表 ──

_plugin_registry: list[type["TransformPlugin"]] = []
# 与 _plugin_registry 平行：每个插件类的**来源组件名**（`grammar/<lang>/plugins/
# <component>/x.py` → `<component>`），引擎插件为 None。用于把插件应用限定在
# 当前语言作用域内——注册表是进程级累积的（组件模块 import 期副作用），不过滤
# 就会让**别的语言的插件参与本语言管线**（实测：同进程先跑 c4 再跑 verilog，
# c4 的 AsmGenPlugin 会作用在 verilog AST 上）。
_plugin_origins: list[str | None] = []
# 限定名 → 类（插件身份面，ADR-0015 §1：插件实例化对象是一等单元，
# 需可寻址 → 管线配置按名引用）与注册序（缺省执行序）。
_plugin_index: dict[str, type["TransformPlugin"]] = {}
# 插件契约（ADR-0015 §3）：限定名 → {produces, requires}——**插件侧注册时声明**，
# 显式平铺列表（同语法 production 列表风格）。未声明 = 不参与校验（可选能力）。
_plugin_contracts: dict[str, dict[str, list[str]]] = {}
# 产物形状声明（阶段 7 切片 2）：限定名 → {产物名: 形状 spec}——引擎机械核验
# （type=dict/list、non_empty），不懂语义；可选能力。
_plugin_shapes: dict[str, dict[str, dict]] = {}


_T = TypeVar("_T", bound="TransformPlugin")

# 形状 spec 支持的机械核验 token（引擎不懂语义，只做类型/非空检查）。
_SHAPE_TYPES = ("dict", "list")


def _validate_shapes(
    qname: str, produces: list[str], shapes: dict[str, dict]
) -> None:
    """形状声明核验（注册期 fail-fast）：键须在 produces；spec 键/取值合法。"""
    for pname, spec in shapes.items():
        if pname not in produces:
            raise ValueError(
                f"[transform] 插件 '{qname}' shapes 键 {pname!r} 不在 produces 声明中"
            )
        if not isinstance(spec, dict):
            raise ValueError(
                f"[transform] 插件 '{qname}' shapes[{pname!r}] 须为表: {spec!r}"
            )
        unknown = set(spec) - {"type", "non_empty"}
        if unknown:
            raise ValueError(
                f"[transform] 插件 '{qname}' shapes[{pname!r}] 未知键: "
                f"{', '.join(sorted(unknown))}（支持 type/non_empty）"
            )
        stype = spec.get("type")
        if stype is not None and stype not in _SHAPE_TYPES:
            raise ValueError(
                f"[transform] 插件 '{qname}' shapes[{pname!r}].type 非法: {stype!r}"
                f"（支持 {_SHAPE_TYPES}）"
            )
        if "non_empty" in spec and not isinstance(spec["non_empty"], bool):
            raise ValueError(
                f"[transform] 插件 '{qname}' shapes[{pname!r}].non_empty 须为布尔"
            )


@overload
def register_plugin(
    cls: type[_T],
    *,
    name: str | None = None,
    produces: list[str] | None = None,
    requires: list[str] | None = None,
    shapes: dict[str, dict] | None = None,
) -> type[_T]: ...


@overload
def register_plugin(
    cls: None = None,
    *,
    name: str | None = None,
    produces: list[str] | None = None,
    requires: list[str] | None = None,
    shapes: dict[str, dict] | None = None,
) -> Callable[[type[_T]], type[_T]]: ...


def register_plugin(
    cls: type["TransformPlugin"] | None = None,
    *,
    name: str | None = None,
    produces: list[str] | None = None,
    requires: list[str] | None = None,
    shapes: dict[str, dict] | None = None,
) -> Any:
    """装饰器：注册一个变换插件类（可带限定名 + 契约声明）。

    Usage:
        @register_plugin                        # 名 = 类名，无契约
        class MyPlugin(TransformPlugin): ...

        @register_plugin(name="typed_ports.bridge", requires=["scope"])
        class ComponentSlotPlugin(TransformPlugin): ...

    契约（produces/requires）= 显式平铺名列表（引擎只做机械核验，不懂语义）；
    `shapes` = 可选的产物形状声明（`{产物名: {"type": "dict"|"list",
    "non_empty": bool}}`，键须在 produces；注册期 fail-fast，执行后核验）。
    **不含时点**——时点只在管线配置（`[pipeline.units.*]`）里编排（ADR-0015 §1）。
    重名 → 索引取**首个注册者**（同一插件文件被多路径 import 时类对象不同名同，
    是既有常态，不报错）；`_plugin_registry` 保留全部注册（不动现状执行序）。
    """

    def _register(klass: type["TransformPlugin"]) -> type["TransformPlugin"]:
        qname = name or klass.__name__
        if shapes:
            _validate_shapes(qname, list(produces or []), shapes)
        # 索引：首胜（按名引用取注册序首个）；registry：照旧全注册
        _plugin_index.setdefault(qname, klass)
        _plugin_registry.append(klass)
        _plugin_origins.append(_origin_component(klass))
        contract = {
            "produces": list(produces or []),
            "requires": list(requires or []),
        }
        if contract["produces"] or contract["requires"]:
            _plugin_contracts.setdefault(qname, contract)
        if shapes:
            _plugin_shapes.setdefault(
                qname, {k: dict(v) for k, v in shapes.items()}
            )
        return klass

    if cls is not None:
        return _register(cls)
    return _register


def _origin_component(klass: type) -> str | None:
    """插件类的来源组件名（非语言插件 → None）。

    按模块文件路径判定：`.../grammar/<lang>/plugins/<component>/x.py` →
    `<component>`；引擎插件（`transform/*.py`）→ None。路径判定不依赖模块名
    （组件模块名是 `_comp_<组件>_<文件>` 的合成名，且同一文件可能被直接 import）。
    """
    mod = sys.modules.get(klass.__module__)
    path = str(getattr(mod, "__file__", "") or "").replace("\\", "/")
    parts = path.split("/")
    if "grammar" not in parts or "plugins" not in parts:
        return None
    idx = len(parts) - 1 - parts[::-1].index("plugins")  # 最后一个 plugins
    if idx + 1 < len(parts) - 1:  # 至少还有 <component>/<file>
        return parts[idx + 1]
    return None


def active_plugin_classes() -> list[type["TransformPlugin"]]:
    """当前语言作用域内的插件类：引擎插件 + 当前已装载组件声明的插件。

    注册表是进程级累积的（见 `core/global_state.py` 的 ACCUMULATED 表），累积
    本身不安全——`AstTransformer` 会**实例化并执行**登记的全部插件；安全来自
    应用侧按语言作用域过滤（插件是否有根节点守卫属各插件自行约定，不能当机制
    保障）。未建立语言作用域时（纯单测直接 import 插件模块）不过滤。
    """
    from core.plugin_loader import _active_components, _components_initialized

    if not _components_initialized:
        return list(_plugin_registry)
    return [
        cls
        for cls, origin in zip(_plugin_registry, _plugin_origins)
        if origin is None or origin in _active_components
    ]


def get_plugin_contracts() -> dict[str, dict[str, list[str]]]:
    """已注册插件的契约声明（限定名 → {produces, requires}），无声明者不在内。"""
    return {k: dict(v) for k, v in _plugin_contracts.items()}


def get_plugin_shapes() -> dict[str, dict[str, dict]]:
    """已注册插件的产物形状声明（限定名 → {产物名: spec}），无声明者不在内。"""
    return {k: {n: dict(s) for n, s in v.items()} for k, v in _plugin_shapes.items()}


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

    def note_produced(self, name: str, obj: Any = None) -> None:
        """登记物化产物（契约校验，阶段 7）：声明 `produces` 的生产方在
        `process` 内调用（未产出不得声明）；`obj` 供形状核验（可选）。

        无 transformer（直接 process 的单元测试）时空操作。
        """
        if self._transformer is not None:
            self._transformer.note_produced(name, obj)


class AstTransformer:
    """后阶段变换管线，依次执行所有已注册的插件"""

    _shared_ctx: ClassVar[dict[str, Any]] = {}

    def __init__(self, plugins: list[TransformPlugin] | None = None):
        if plugins is not None:
            self._plugins = list(plugins)
        else:
            # 从全局注册表自动实例化**当前语言作用域内**的插件（引擎插件 +
            # 当前已装载组件声明的插件；见 active_plugin_classes）
            self._plugins = [cls() for cls in active_plugin_classes()]
        # 物化登记（契约校验，阶段 7 切片 2）：产物名 → 对象（可为 None）
        self._produced: dict[str, Any] = {}

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

    def note_produced(self, name: str, obj: Any = None) -> None:
        """登记物化产物（插件经 `TransformPlugin.note_produced` 调用；契约校验用）。

        引擎只记录名与对象（形状核验用），不懂语义（ADR-0015 §3 姿态）。
        同时发布到共享产物通道（`_shared_ctx["productions"]`，由调度按单元时点
        累积）——消费方按契约名取用，**不必与生产方在同一 transformer 实例**。
        """
        self._produced[name] = obj
        published = self._shared_ctx.get("productions")
        if isinstance(published, dict):
            published[name] = obj

    def produced(self) -> dict[str, Any]:
        """本 transformer 生命周期内登记的物化产物（名 → 对象，对象可为 None）。"""
        return dict(self._produced)

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
