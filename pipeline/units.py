"""pipeline/units.py — 加工单元实例 + 统一时点生成。

**统一调度**：analyze 与 transform 不再是两类 pass，而是**同一种加工单元实例**
（`type` 表达角色）——"分析产出一个分析结果或一个执行回调，随后跟一个执行"。
**单元粒度 = 插件级**（引擎内置原语不对外暴露为单元）。

**时点由调度器统一生成**：输入 = 管线配置 + 所有单元实例的声明参数
（`order=N` 显式钉号 / `after=X` 推导 / 无约束按声明序填空），与 pass 级同构；
冲突 / `after` 环 / 未知引用 → 诊断 + fail-fast（不静默降级）。

**配对（分析 → 执行）隐式**（时点相邻 + `scope`/`extra` 通道），但产物必须
**可视化**（`pipeline/README.md`「时点轨迹报告」）。

Doc: pipeline/README.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_TYPES = ("analyze", "transform", "check")

# 内置单元 impl 约定（粗粒度执行器；插件级细粒度见 5b-3）
BUILTIN_IMPLS = frozenset({"builtin.analyze", "builtin.transform"})

# impl 引用形态（插件实例化对象是一等单元 → 可寻址）
IMPL_BUILTIN = "builtin"
IMPL_HANDLER = "handler"
IMPL_PLUGIN = "plugin"


def classify_impl(impl: str) -> str:
    """判定 impl 引用形态（只判形态，存在性由调度层校验）。

    `builtin.*` → 内置执行器；含 `:` → `file.py:fn` 处理器引用；
    其余 → 变换插件限定名（`transform.engine.get_plugin_index()`）。
    """
    if impl.startswith("builtin."):
        return IMPL_BUILTIN
    if ":" in impl:
        return IMPL_HANDLER
    return IMPL_PLUGIN


@dataclass
class UnitInstance:
    """一个加工单元实例（显式声明：类型 / 实现 / 时点声明 / 参数）。

    `impl` 与 `slot` 互斥：前者引用插件/内置执行器/处理器；后者是**槽位级单元**
    （`[[transform.slots]]` 声明的槽位，由引擎 `slot_runner` 单槽位执行 → 各自
    独立时点，ADR-0015 §1）。
    """

    name: str
    type: str
    impl: str = ""
    after: str | None = None
    order: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    slot: str | None = None
    point: int = -1  # 调度器生成的时点号（assign_points 填充）


def _check_slot_impl(name: str, slot, impl: str) -> None:
    """slot 与 impl 互斥且至少有一个（槽位单元用 slot；插件/执行器用 impl）。"""
    if slot is None:
        if not impl:
            raise ValueError(f"[pipeline] unit '{name}' 缺 impl 或 slot")
        return
    if not isinstance(slot, str) or not slot:
        raise ValueError(f"[pipeline] unit '{name}' slot 须为非空字符串")
    if impl:
        raise ValueError(
            f"[pipeline] unit '{name}' slot 与 impl 互斥"
            f"（槽位单元用 slot；插件/执行器用 impl）"
        )


def _unit_slot_impl(name: str, decl: dict) -> tuple[str, Any, str]:
    """type / slot / impl 三字段校验 → (type, slot, impl)。"""
    utype = decl.get("type", "")
    impl = decl.get("impl", "")
    slot = decl.get("slot")
    if utype not in VALID_TYPES:
        raise ValueError(
            f"[pipeline] unit '{name}' type 非法: {utype!r}（合法: {VALID_TYPES}）"
        )
    _check_slot_impl(name, slot, impl)
    if impl and classify_impl(impl) == IMPL_BUILTIN and impl not in BUILTIN_IMPLS:
        raise ValueError(
            f"[pipeline] unit '{name}' impl 非内置执行器: {impl!r}"
            f"（合法: {sorted(BUILTIN_IMPLS)}）"
        )
    return utype, slot, impl


def _unit_timing(name: str, decl: dict) -> tuple[Any, Any]:
    """after / order 两字段校验 → (after, order)（互斥；order 须非负整数）。"""
    after = decl.get("after")
    order = decl.get("order")
    if after is not None and order is not None:
        raise ValueError(f"[pipeline] unit '{name}' after 与 order 互斥")
    if order is not None and (
        not isinstance(order, int) or isinstance(order, bool) or order < 0
    ):
        raise ValueError(f"[pipeline] unit '{name}' order 须为非负整数: {order!r}")
    return after, order


def _unit_params(name: str, decl: dict) -> dict:
    """params 字段校验 → 键为字符串的表。"""
    params = decl.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError(f"[pipeline] unit '{name}' params 须为表: {params!r}")
    if any(not isinstance(k, str) for k in params):
        raise ValueError(f"[pipeline] unit '{name}' params 键须为字符串: {params!r}")
    return dict(params)


def _parse_unit(name: str, decl: dict) -> UnitInstance:
    """单条单元声明 → UnitInstance（逐字段 fail-fast）。"""
    if not isinstance(decl, dict):
        raise ValueError(f"[pipeline] unit '{name}' 声明须为表: {decl!r}")
    utype, slot, impl = _unit_slot_impl(name, decl)
    after, order = _unit_timing(name, decl)
    return UnitInstance(
        name=name,
        type=utype,
        impl=impl,
        after=after,
        order=order,
        params=_unit_params(name, decl),
        slot=slot,
    )


def parse_units(decls: dict[str, dict]) -> list[UnitInstance]:
    """解析 `[pipeline.units.<name>]` 声明 → 单元实例列表（保持声明序）。

    fail-fast：声明非表 / type 非法 / 缺 impl / slot 与 impl 并存 / order 与 after
    并存 / order 非法 / params 非表或键非字符串——逐字段判据见 `_parse_unit` 与
    `_unit_slot_impl` / `_unit_timing` / `_unit_params`。
    """
    return [_parse_unit(name, decl) for name, decl in (decls or {}).items()]


def _check_unique_names(units: list[UnitInstance]) -> set[str]:
    """单元名唯一（重复 → 报错）；返回名字集合。"""
    names = [u.name for u in units]
    if len(set(names)) != len(names):
        raise ValueError("[pipeline] 单元名重复")
    return set(names)


def _check_after_refs(units: list[UnitInstance], valid: set[str]) -> None:
    """after 引用的单元须存在。"""
    for u in units:
        if u.after is not None and u.after not in valid:
            raise ValueError(
                f"[pipeline] unit '{u.name}' after 引用未声明单元: {u.after!r}"
            )


def _pin_point(name: str, point: int, point_of: dict[str, int]) -> None:
    """占点；已被占用 → 报错（需用 order 或 after 分先后）。"""
    if point in point_of.values():
        raise ValueError(
            f"[pipeline] unit '{name}' 落点 {point} 已被占用，"
            "需用 order 或 after 分先后"
        )
    point_of[name] = point


def _pin_declared_orders(units: list[UnitInstance], point_of: dict[str, int]) -> None:
    """1. 显式 order 钉号。"""
    for u in units:
        if u.order is not None:
            _pin_point(u.name, u.order, point_of)


def _fill_declared_order(units: list[UnitInstance], point_of: dict[str, int]) -> None:
    """2. 声明序走查：无约束条目填空下一个空闲点；after 目标已知则落 target+1。"""
    next_free = 0
    for u in units:
        if u.name in point_of:
            continue
        if u.after is None:
            while next_free in point_of.values():
                next_free += 1
            point_of[u.name] = next_free
        elif u.after in point_of:
            _pin_point(u.name, point_of[u.after] + 1, point_of)


def _resolve_remaining(units: list[UnitInstance], point_of: dict[str, int]) -> None:
    """3. 迭代解析剩余 after 至不动点；仍有未解析 → after 环/不可达（报错）。"""
    changed = True
    while changed:
        changed = False
        for u in units:
            if u.name in point_of or u.after is None:
                continue
            if u.after in point_of:
                _pin_point(u.name, point_of[u.after] + 1, point_of)
                changed = True
    unresolved = [u.name for u in units if u.name not in point_of]
    if unresolved:
        raise ValueError(f"[pipeline] unit after 环/不可达: {unresolved}")


def assign_points(units: list[UnitInstance]) -> list[UnitInstance]:
    """统一时点生成（与 pass 级同构的三步推导）+ 诊断；就地填 `point` 并返回点序列表。

    1. `order=N` 显式钉号（占位冲突 → 报错）；
    2. 声明序走查：无约束条目填空下一个空闲点；`after=X` 目标已知则落 target+1；
    3. 迭代解析剩余 `after` 至不动点；仍有未解析 → `after` 环（报错）。
    """
    valid = _check_unique_names(units)
    _check_after_refs(units, valid)
    point_of: dict[str, int] = {}
    _pin_declared_orders(units, point_of)
    _fill_declared_order(units, point_of)
    _resolve_remaining(units, point_of)
    for u in units:
        u.point = point_of[u.name]
    return sorted(units, key=lambda u: u.point)


def build_unit_sequence(decls: dict[str, dict] | None) -> list[UnitInstance]:
    """从声明（`[pipeline] units` 汇总表）构建**有序单元序列**（时点已生成）。

    入口：`core.plugin_loader.get_pipeline_units()` 的汇总结果（或测试直接喂）。
    """
    return assign_points(parse_units(decls or {}))


def validate_sequence(units: list[UnitInstance]) -> None:
    """序列限定（5b-3a/5b-3c-3）：粗粒度与细粒度共存规则。

    - `analyze`：至多 1 个（分析遍历是一个整体，多实例无意义）；
    - `transform`：要么单个 `builtin.transform`（粗粒度：跑全部插件），
      要么全为插件/槽位单元（细粒度：各自一个时点）；**两者混用**会重复
      执行（插件/槽位被跑两次）→ fail-fast。
    - `check`：不限个数（可多实例）。同一插件/槽位多单元 = 同一变换多时点。
    """
    analyze_count = sum(1 for u in units if u.type == "analyze")
    if analyze_count > 1:
        raise ValueError(
            f"[pipeline] type='analyze' 单元至多 1 个（当前 {analyze_count} 个）"
        )
    tf_units = [u for u in units if u.type == "transform"]
    builtin_tf = [u for u in tf_units if u.impl in BUILTIN_IMPLS]
    if builtin_tf and len(tf_units) > 1:
        raise ValueError(
            f"[pipeline] transform 单元 '{builtin_tf[0].name}'（builtin.transform）"
            "与其余 transform 单元共存会重复执行——要么单个 builtin.transform，"
            "要么全部用插件/槽位单元"
        )
