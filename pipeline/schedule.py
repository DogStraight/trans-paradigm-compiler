"""schedule.py — 编排管线（pass 声明 + 时点序列器 + 调度构建）。

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

本模块 = 编排器（一个文件闭环）：声明处理 + 时点排序 + 执行
（_run_schedule 与 pass 执行器 _run_pass_*）。执行依赖的共享实例
（schedules / mapping_cfg）由调用方注入，不触碰管线模块状态，
可独立于 run_pipeline_on_source 复用（如未来 tpc-check 模式）。

fail-fast（不静默降级，见 core/config_lifecycle.md）：未知 pass / 重名 / 时点
冲突 / after 环 / check 缺 handler 全部报 ValueError，不静默降级。

Doc: docs/pipeline_stages.md
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from core.plugin_loader import (
    get_capability,
    get_pipeline_pass_decls,
    get_pipeline_schedules,
)
from core.utils import save_json
from analyzer import AnalysisTraversal
from transform import AstTransformer

BUILTIN_PASSES: dict[str, dict] = {
    "analyze": {"kind": "analyze"},
    "transform": {"kind": "transform"},
}

_KINDS = ("analyze", "transform", "check")

DEFAULT_SCHEDULE_NAME = "default"
DEFAULT_SCHEDULE_ENTRIES = ["analyze", "transform"]

# 编排器公共面（含跨模块使用的私有名——同包兄弟模块 import 的实现契约）
__all__ = [
    "PassDecl",
    "PassState",
    "build_schedules",
    "_run_schedule",
    "_LEGACY_PASS_STAGES",
    "DEFAULT_SCHEDULE_NAME",
    "DEFAULT_SCHEDULE_ENTRIES",
]


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


# ── 执行（ADR-0007）────────────────────────────────────────


def build_unit_schedule(unit_decls: dict[str, dict]) -> list["PassDecl"] | None:
    """把 `[pipeline] units` 声明构建为**可执行单元序列**（粗粒度，5b-2）。

    返回 None = 无声明（调用方回落 pass 序列）。impl 约定：
      `builtin.analyze` / `builtin.transform` → 内置执行器（由 `kind` 驱动）；
      其余 → 加载时已解析的 handler（`_handler`，check 类）。
    单元与 pass 在执行层同构（都是 `PassDecl`：name/kind/handler）→ 直接复用
    `_run_schedule` 的分派，无需另写执行器。
    """
    if not unit_decls:
        return None
    from .units import BUILTIN_IMPLS, build_unit_sequence, validate_sequence

    units = build_unit_sequence(unit_decls)
    validate_sequence(units)

    out: list[PassDecl] = []
    for u in units:
        decl = unit_decls.get(u.name) or {}
        handler = decl.get("_handler")
        if u.impl not in BUILTIN_IMPLS and handler is None:
            raise ValueError(
                f"[pipeline] unit '{u.name}' impl 未解析为 handler: {u.impl!r}"
            )
        out.append(PassDecl(name=u.name, kind=u.type, handler=handler))
    return out


class _ScheduleStop(Exception):
    """内部控制流：pass 请求终止调度（analyze 报 error 级诊断）。"""


def _run_pass_analyze(state: "PassState") -> None:
    """kind=analyze pass：跑一轮 AnalysisTraversal，覆盖 scope。

    error 级诊断 → 置 ctx.result["error"] 并抛 _ScheduleStop（停调度停管线）。
    """
    ctx = state.ctx
    analyzer = AnalysisTraversal(ctx.rules)
    state.ast = analyzer.analyze(state.ast)
    state.analyzer = analyzer
    state.scope = analyzer.root_scope
    if analyzer.root_scope is None:
        ctx.log("[analyzer] warning: no scope produced")
    else:
        if not ctx.quiet:
            if ctx.sym_json:
                save_json(
                    analyzer.root_scope.to_dict(), ctx.sym_json, "symbols",
                    log_fn=ctx.log
                )
            # Dump transform callbacks (_ref_callbacks) to trans_callback/
            # 经能力查找（P2.5）接入——typed_ports 声明
            # [capabilities] transform_callbacks；非 verilog 语言无此能力
            # 时 get_capability 返回 None，回调收集降级为空。
            collect_cbs = get_capability("transform_callbacks")
            callbacks = collect_cbs(analyzer.root_scope) if collect_cbs else {}
            if callbacks and ctx.cb_json:
                save_json(callbacks, ctx.cb_json, "callbacks", log_fn=ctx.log)
        ctx.log(f"[symbols] {len(analyzer.all_symbols)} symbols")
    if analyzer.has_errors:
        for d in analyzer.diagnostics:
            ctx.log(f"[analyzer] {d}")
        if any(d.level == "error" for d in analyzer.diagnostics):
            ctx.result["error"] = "; ".join(
                str(d) for d in analyzer.diagnostics if d.level == "error"
            )
            ctx.log("[analyzer] semantic errors, stopping pipeline")
            raise _ScheduleStop()


def _run_pass_transform(
    state: "PassState", mapping_cfg: dict | None = None
) -> None:
    """kind=transform pass：跑一轮 AstTransformer（消费 scope，None 跳过）。

    mapping_cfg 由调用方注入（_ensure_shared 按 rules_dir 缓存构建），
    不依赖全局 _loaded_components（可能被其他语言包污染）。
    """
    ctx = state.ctx
    if state.scope is None:
        ctx.log("[transform] skipped (no scope)")
        return
    AstTransformer.set_shared("rules", ctx.rules)
    AstTransformer.set_shared("mapping_cfg", mapping_cfg or {})
    transformer = AstTransformer()
    state.transformer = transformer

    # 一次 transform 完成：映射表构建 + 配置变换
    state.ast = transformer.transform(state.ast, state.scope)

    # 收集变换统计
    parts = []
    for plugin in transformer.plugins:
        if hasattr(plugin, "stats"):
            s = plugin.stats
            for k, v in s.items():
                if v:
                    parts.append(f"{k}={v}")
    if parts:
        ctx.log(f"[transform] {' '.join(parts)}")


def _run_pass_check(state: "PassState", decl: "PassDecl") -> None:
    """kind=check pass：执行插件 handler（fn(state) -> None）。

    语义：检查/验证/外部工具挂载（不改 AST，可读改 scope/extra 产诊断）。
    """
    assert decl.handler is not None
    decl.handler(state)


_LEGACY_PASS_STAGES = ("analyze", "transform")


def _run_schedule(
    ctx: Any,
    ast: Any,
    scope: Any,
    schedule_name: str,
    schedules: dict[str, list[PassDecl]],
    mapping_cfg: dict | None = None,
) -> tuple[Any, Any]:
    """按命名 schedule 执行 pass 序列（ADR-0007）。返回 (ast, scope)。

    - schedules / mapping_cfg 由调用方注入（管线按 rules_dir 缓存的实例）。
    - expand_enhanced=False → 跳过整个调度（保留增强语法直渲）。
    - 开关过滤：analyzer_enabled=False 滤 kind=analyze；transform_enabled
      同理。
    - stage 命中 pass 名 → 执行该 pass 后截断（legacy "analyze"/
      "transform" 按内置 pass 名匹配）。
    - _ScheduleStop → 截断调度（error 已写入 ctx.result）。
    """
    if not ctx.expand_enhanced:
        ctx.log("[pipeline] enhanced-expansion disabled: preserving enhanced syntax")
        return ast, None

    if schedule_name not in schedules:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 未声明"
            f"（可用: {', '.join(sorted(schedules)) or '(空)'}）"
        )
    state = PassState(ast=ast, scope=scope, ctx=ctx)
    for decl in schedules[schedule_name]:
        if decl.kind == "analyze" and not ctx.analyzer_enabled:
            ctx.log(f"[pipeline] pass '{decl.name}' skipped (analyze disabled)")
            continue
        if decl.kind == "transform" and not ctx.transform_enabled:
            ctx.log(f"[pipeline] pass '{decl.name}' skipped (transform disabled)")
            continue
        ctx.log(f"[pipeline] pass: {decl.name}")
        try:
            if decl.kind == "analyze":
                _run_pass_analyze(state)
            elif decl.kind == "transform":
                _run_pass_transform(state, mapping_cfg)
            else:
                _run_pass_check(state, decl)
        except _ScheduleStop:
            break
        if ctx.stage == decl.name:
            break
    return state.ast, state.scope
