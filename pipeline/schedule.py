"""schedule.py — 编排管线（ADR-0007）：pass 声明 + 时点序列器 + 调度构建。

概念：
    pass      — 命名的执行单元，kind ∈ {analyze, transform, check}。
                操作（原语/变换）不携带时点，时点是 pass 级概念。
    schedule  — 命名的 pass 序列（编排管线），调用方按名称启用。
    slot      — 时点号（schedule 内相对位置）。order=N 显式钉号；
                after=X 由序列器推导为 slot(X)+1；无约束按声明序顺延。

kind 语义（行为模型）：
    analyze   — 跑一轮 AnalysisTraversal（产出 scope）；
    transform — 跑一轮 AstTransformer（消费 scope 改 AST）；
    check     — 执行插件 handler（检查/验证/外部工具挂载，不改 AST）。
后续需要新行为模型时扩展 _KINDS 枚举 + pipeline/__init__.py 执行分支，
不引入泛化类型（如 custom）。

本模块只做**声明处理与排序**（纯逻辑，可单测）；执行编排在
pipeline/__init__.py::_run_schedule。

fail-fast（ADR-0003）：未知 pass / 重名 / 时点冲突 / after 环 /
check 缺 handler 全部报 ValueError，不静默降级。

Doc: docs/decisions/0007-pipeline-schedule.md
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from core.plugin_loader import get_pipeline_pass_decls, get_pipeline_schedules

BUILTIN_PASSES: dict[str, dict] = {
    "analyze": {"kind": "analyze"},
    "transform": {"kind": "transform"},
}

_KINDS = ("analyze", "transform", "check")

DEFAULT_SCHEDULE_NAME = "default"
DEFAULT_SCHEDULE_ENTRIES = ["analyze", "transform"]


@dataclass
class PassDecl:
    """一个已解析的 pass 定义。"""

    name: str
    kind: str  # analyze | transform | check
    handler: Callable | None = None  # check pass 的执行函数（已解析）


@dataclass
class PassState:
    """pass 执行状态（调度内线程，check handler 可读改）。"""

    ast: Any
    scope: Any | None
    ctx: Any  # _PipelineContext（日志/结果/输出目录等）
    analyzer: Any | None = None  # 最近一轮 analyze 的 AnalysisTraversal
    transformer: Any | None = None  # 最近一轮 transform 的 AstTransformer
    extra: dict = field(default_factory=dict)  # pass 间自定义通道


def _sequence_entries(
    entries: list, schedule_name: str, valid_names: set[str]
) -> list[str]:
    """时点序列器：把 schedule 的 passes 条目解析为有序 pass 名列表。

    条目形态：str（名字）或 dict（name + order | after，二者互斥）。
    slot 推导（三步）：
        1. order = N 显式钉号（互相冲突报错）；
        2. 按声明序走查：默认条目填空下一个空闲 slot（跳过已钉号）；
           after 条目目标已知则立即落 slot(target)+1；
        3. 剩余 after 条目迭代解析，直至不动点；
           仍有未解析 → after 环（报错）。
    冲突检测：两个条目落同一 slot → ValueError（"需分前后"）。
    """
    norm: list[dict] = []
    seen_names: set[str] = set()
    for e in entries:
        if isinstance(e, str):
            name, order, after = e, None, None
        elif isinstance(e, dict):
            name = e.get("name")
            order = e.get("order")
            after = e.get("after")
            if order is not None and after is not None:
                raise ValueError(
                    f"[pipeline] schedule '{schedule_name}' 条目 {name!r} "
                    f"order 与 after 互斥"
                )
        else:
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' 条目形态非法: {e!r}"
            )
        if not isinstance(name, str) or name not in valid_names:
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' 引用未声明的 pass: "
                f"{name!r}"
            )
        if name in seen_names:
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' 重复引用 pass: {name}"
            )
        seen_names.add(name)
        if order is not None and (
            not isinstance(order, int) or isinstance(order, bool) or order < 0
        ):
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' order 须为非负整数: "
                f"{order!r}"
            )
        if after is not None and after not in valid_names:
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' after 引用未声明的 "
                f"pass: {after!r}"
            )
        norm.append({"name": name, "order": order, "after": after})

    slot_of: dict[str, int] = {}

    def _conflict(name: str, s: int) -> None:
        if s in slot_of.values():
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' 时点冲突: "
                f"pass '{name}' 落 slot {s}（已被占用），"
                f"需用 order 或 after 分前后"
            )

    # 1. 显式 order 钉号
    for e in norm:
        if e["order"] is not None:
            _conflict(e["name"], e["order"])
            slot_of[e["name"]] = e["order"]

    # 2. 声明序走查：默认条目填空 + after 即时解析
    next_free = 0
    deferred: list[dict] = []
    for e in norm:
        if e["name"] in slot_of:
            continue
        if e["after"] is None:
            while next_free in slot_of.values():
                next_free += 1
            slot_of[e["name"]] = next_free
            next_free += 1
        elif e["after"] in slot_of:
            s = slot_of[e["after"]] + 1
            _conflict(e["name"], s)
            slot_of[e["name"]] = s
        else:
            deferred.append(e)

    # 3. 迭代解析剩余 after 直至不动点
    while deferred:
        progressed = False
        for e in list(deferred):
            if e["after"] in slot_of:
                s = slot_of[e["after"]] + 1
                _conflict(e["name"], s)
                slot_of[e["name"]] = s
                deferred.remove(e)
                progressed = True
        if not progressed:
            chain = " -> ".join(
                sorted(e["name"] for e in deferred)
            )
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' after 环: {chain}"
            )

    by_slot = {s: n for n, s in slot_of.items()}
    return [by_slot[s] for s in sorted(by_slot)]


def build_schedules() -> dict[str, list[PassDecl]]:
    """构建全部 schedule：内置缺省 + 插件声明（经 plugin_loader 合并）。

    返回 {schedule 名: [PassDecl 执行序]}。无任何声明时仅含
    default = [analyze, transform]（现行为）。
    """
    # 1. pass 声明：内置 + 插件
    pass_decls: dict[str, dict] = dict(BUILTIN_PASSES)
    for name, decl in get_pipeline_pass_decls().items():
        if name in pass_decls:
            raise ValueError(
                f"[pipeline] pass 名 '{name}' 与内置/已声明 pass 冲突"
            )
        pass_decls[name] = decl

    resolved: dict[str, PassDecl] = {}
    for name, decl in pass_decls.items():
        kind = decl.get("kind", name if name in BUILTIN_PASSES else "")
        if kind not in _KINDS:
            raise ValueError(
                f"[pipeline] pass '{name}' kind 非法: {kind!r} "
                f"（应为 analyze/transform/check）"
            )
        handler = decl.get("_handler")
        if kind == "check" and handler is None:
            raise ValueError(
                f"[pipeline] check pass '{name}' 缺 handler "
                f"（handler = \"file.py:fn\"）"
            )
        resolved[name] = PassDecl(name=name, kind=kind, handler=handler)

    # 2. schedule 声明：序列化
    schedules: dict[str, list[PassDecl]] = {}
    decl_schedules = get_pipeline_schedules()
    for sname, sdecl in decl_schedules.items():
        ordered = _sequence_entries(
            sdecl.get("passes", []), sname, set(resolved)
        )
        schedules[sname] = [resolved[n] for n in ordered]

    # 3. 缺省 schedule（未声明时 = 现行为）
    if DEFAULT_SCHEDULE_NAME not in schedules:
        ordered = _sequence_entries(
            DEFAULT_SCHEDULE_ENTRIES, DEFAULT_SCHEDULE_NAME, set(resolved)
        )
        schedules[DEFAULT_SCHEDULE_NAME] = [resolved[n] for n in ordered]
    return schedules
