"""pipeline/units.py — 加工单元实例 + 统一时点生成（ADR-0015 §1）。

**统一调度**：analyze 与 transform 不再是两类 pass，而是**同一种加工单元实例**
（`type` 表达角色）——"分析产出一个分析结果或一个执行回调，随后跟一个执行"。
**单元粒度 = 插件级**（引擎内置原语不对外暴露为单元）。

**时点由调度器统一生成**：输入 = 管线配置 + 所有单元实例的声明参数
（`order=N` 显式钉号 / `after=X` 推导 / 无约束按声明序填空），与 pass 级同构；
冲突 / `after` 环 / 未知引用 → 诊断 + fail-fast（不静默降级）。

**配对（分析 → 执行）隐式**（时点相邻 + `scope`/`extra` 通道），但产物必须
**可视化**（§2 可视化管道与其绑定）。

Doc: docs/decisions/0015-middle-stage-governance.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_TYPES = ("analyze", "transform", "check")


@dataclass
class UnitInstance:
    """一个加工单元实例（显式声明：类型 / 实现 / 时点声明 / 参数）。"""

    name: str
    type: str
    impl: str
    after: str | None = None
    order: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    point: int = -1  # 调度器生成的时点号（assign_points 填充）


def parse_units(decls: dict[str, dict]) -> list[UnitInstance]:
    """解析 `[pipeline.units.<name>]` 声明 → 单元实例列表（保持声明序）。

    fail-fast：声明非表 / type 非法 / 缺 impl / order 与 after 并存 / order 非法。
    """
    units: list[UnitInstance] = []
    for name, decl in (decls or {}).items():
        if not isinstance(decl, dict):
            raise ValueError(f"[pipeline] unit '{name}' 声明须为表: {decl!r}")
        utype = decl.get("type", "")
        impl = decl.get("impl", "")
        if utype not in VALID_TYPES:
            raise ValueError(
                f"[pipeline] unit '{name}' type 非法: {utype!r}（合法: {VALID_TYPES}）"
            )
        if not impl:
            raise ValueError(f"[pipeline] unit '{name}' 缺 impl")
        after = decl.get("after")
        order = decl.get("order")
        if after is not None and order is not None:
            raise ValueError(f"[pipeline] unit '{name}' after 与 order 互斥")
        if order is not None and (
            not isinstance(order, int) or isinstance(order, bool) or order < 0
        ):
            raise ValueError(f"[pipeline] unit '{name}' order 须为非负整数: {order!r}")
        units.append(
            UnitInstance(
                name=name,
                type=utype,
                impl=impl,
                after=after,
                order=order,
                params=dict(decl.get("params") or {}),
            )
        )
    return units


def assign_points(units: list[UnitInstance]) -> list[UnitInstance]:
    """统一时点生成（与 pass 级同构的三步推导）+ 诊断；就地填 `point` 并返回点序列表。

    1. `order=N` 显式钉号（占位冲突 → 报错）；
    2. 声明序走查：无约束条目填空下一个空闲点；`after=X` 目标已知则落 target+1；
    3. 迭代解析剩余 `after` 至不动点；仍有未解析 → `after` 环（报错）。
    """
    names = [u.name for u in units]
    if len(set(names)) != len(names):
        raise ValueError("[pipeline] 单元名重复")
    valid = set(names)

    for u in units:
        if u.after is not None and u.after not in valid:
            raise ValueError(
                f"[pipeline] unit '{u.name}' after 引用未声明单元: {u.after!r}"
            )

    point_of: dict[str, int] = {}

    def _pin(name: str, point: int) -> None:
        if point in point_of.values():
            raise ValueError(
                f"[pipeline] unit '{name}' 落点 {point} 已被占用，"
                "需用 order 或 after 分先后"
            )
        point_of[name] = point

    # 1. 显式 order 钉号
    for u in units:
        if u.order is not None:
            _pin(u.name, u.order)

    # 2. 声明序走查
    next_free = 0
    for u in units:
        if u.name in point_of:
            continue
        if u.after is None:
            while next_free in point_of.values():
                next_free += 1
            point_of[u.name] = next_free
        elif u.after in point_of:
            _pin(u.name, point_of[u.after] + 1)

    # 3. 迭代解析剩余 after 至不动点
    changed = True
    while changed:
        changed = False
        for u in units:
            if u.name in point_of or u.after is None:
                continue
            if u.after in point_of:
                _pin(u.name, point_of[u.after] + 1)
                changed = True

    unresolved = [u.name for u in units if u.name not in point_of]
    if unresolved:
        raise ValueError(f"[pipeline] unit after 环/不可达: {unresolved}")

    for u in units:
        u.point = point_of[u.name]
    return sorted(units, key=lambda u: u.point)
