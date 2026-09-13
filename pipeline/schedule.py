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
    """一个已解析的 pass 定义。

    handler 仅 check 类使用；plugin 仅 transform 类使用（插件限定名，
    非空 = 本单元只跑该插件，插件级单元，ADR-0015 §1）；slot 非空 = 槽位级
    单元（只跑该槽位，由引擎 `slot_runner` 承担，5b-3c-3）。
    impl = 原始 impl 引用（builtin.* / file.py:fn / 插件名 / `slot:<槽位名>`），
    供契约查询与 trace；params = 插件单元实例化参数（构造器关键字参数覆写，
    5b-3b；空 = 默认构造）。
    """

    name: str
    kind: str  # analyze | transform | check
    handler: Callable | None = None  # check pass 的执行函数（已解析）
    plugin: str | None = None  # transform 单元绑定的插件限定名
    impl: str | None = None  # 原始 impl 引用（契约查询用）
    slot: str | None = None  # 槽位级单元绑定的槽位名
    params: dict[str, Any] = field(default_factory=dict)  # 插件构造参数覆写（5b-3b）


@dataclass
class PassState:
    """pass 执行状态（调度内线程，check handler 可读改）。"""

    ast: Any
    scope: Any | None
    ctx: Any  # _PipelineContext（日志/结果/输出目录等）
    analyzer: Any | None = None  # 最近一轮 analyze 的 AnalysisTraversal
    transformer: Any | None = None  # 最近一轮 transform 的 AstTransformer
    extra: dict = field(default_factory=dict)  # pass 间自定义通道
    # 单元执行轨迹（阶段 6 可视化：时点 = 可视化断点）——每单元一条
    # {index, name, kind, impl?, slot?, params?, produced?, extra_added,
    #  extra_keys, artifacts?}
    trace: list[dict] = field(default_factory=list)


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
        # 内置 pass 填 impl（= 内置执行器引用）→ trace 可见 + 契约校验可查；
        # 插件 pass 声明里给了 impl 则沿用（契约同样生效）。
        impl = decl.get("impl") or (
            f"builtin.{name}" if name in BUILTIN_PASSES else None
        )
        resolved[name] = PassDecl(
            name=name, kind=kind, handler=handler, impl=impl
        )

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

def _validate_plugin_params(
    unit_name: str, plugin: str, cls: type, params: dict
) -> None:
    """插件实例化参数核验（5b-3b，加载期 fail-fast）。

    插件参数的唯一形态 = **构造器关键字参数**（执行层 `cls(**params)`）。
    与构造器签名不匹配（未知参数 / 缺必需参数）→ 报签名错误，不静默忽略；
    无法取签名（C 扩展等）→ 跳过，留给执行期构造暴露。
    """
    import inspect

    try:
        sig = inspect.signature(cls)
    except (TypeError, ValueError):
        return
    try:
        sig.bind(**params)
    except TypeError as exc:
        raise ValueError(
            f"[pipeline] unit '{unit_name}' params 与插件 '{plugin}' 构造器"
            f"不匹配: {exc}"
        ) from exc

def build_unit_schedule(unit_decls: dict[str, dict]) -> list["PassDecl"] | None:
    """把 `[pipeline] units` 声明构建为**可执行单元序列**。

    返回 None = 无声明（调用方回落 pass 序列）。impl 三形态（5b-3a）：
      `builtin.analyze` / `builtin.transform` → 内置执行器（由 `kind` 驱动）；
      `file.py:fn` → 加载时已解析的 handler（check 类）；
      其余 → 变换插件限定名（插件级单元：本单元只跑该插件），可带 `params`
      （插件构造器关键字参数覆写，5b-3b，签名核验 fail-fast）。
    单元与 pass 在执行层同构（都是 `PassDecl`）→ 直接复用 `_run_schedule`
    的分派，无需另写执行器。
    """
    if not unit_decls:
        return None
    from transform.engine import get_plugin_index
    from core.plugin_loader import get_transform_slot_decls

    from .units import (
        BUILTIN_IMPLS,
        IMPL_PLUGIN,
        build_unit_sequence,
        classify_impl,
        validate_sequence,
    )

    units = build_unit_sequence(unit_decls)
    validate_sequence(units)
    plugin_index = get_plugin_index()
    slot_decls = get_transform_slot_decls()

    out: list[PassDecl] = []
    for u in units:
        decl = unit_decls.get(u.name) or {}
        handler = decl.get("_handler")
        if u.slot:
            # 槽位级单元（5b-3c-3）：只跑该槽位（引擎 slot_runner 单槽位执行）
            if u.type != "transform":
                raise ValueError(
                    f"[pipeline] unit '{u.name}' 声明 slot={u.slot!r}，"
                    f"但 type={u.type!r}（槽位单元限 transform）"
                )
            if u.params:
                raise ValueError(
                    f"[pipeline] unit '{u.name}' 槽位单元不支持 params"
                    f"（运行器固定单槽位执行，无实例化参数）"
                )
            if u.slot not in slot_decls:
                raise ValueError(
                    f"[pipeline] unit '{u.name}' 引用了未声明的槽位: "
                    f"{u.slot!r}（可用: {', '.join(sorted(slot_decls)) or '(空)'}）"
                )
            out.append(
                PassDecl(
                    name=u.name,
                    kind=u.type,
                    slot=u.slot,
                    impl=f"slot:{u.slot}",
                )
            )
            continue
        impl_kind = classify_impl(u.impl)
        if impl_kind == IMPL_PLUGIN:
            if u.type != "transform":
                raise ValueError(
                    f"[pipeline] unit '{u.name}' impl 是插件名（{u.impl!r}），"
                    f"但 type={u.type!r}（插件单元目前限 transform）"
                )
            if u.impl not in plugin_index:
                raise ValueError(
                    f"[pipeline] unit '{u.name}' 引用了未注册的变换插件: "
                    f"{u.impl!r}（可用: {', '.join(sorted(plugin_index)) or '(空)'}）"
                )
            if u.params:
                _validate_plugin_params(
                    u.name, u.impl, plugin_index[u.impl], u.params
                )
            out.append(
                PassDecl(
                    name=u.name,
                    kind=u.type,
                    plugin=u.impl,
                    impl=u.impl,
                    params=u.params,
                )
            )
            continue
        if u.impl not in BUILTIN_IMPLS and handler is None:
            raise ValueError(
                f"[pipeline] unit '{u.name}' impl 未解析为 handler: {u.impl!r}"
            )
        if u.params:
            raise ValueError(
                f"[pipeline] unit '{u.name}' 内置/处理器单元不支持 params"
                f"（实例化参数覆写仅插件单元）"
            )
        out.append(
            PassDecl(name=u.name, kind=u.type, handler=handler, impl=u.impl)
        )
    return out


# 内置单元契约（引擎级产物名，非语言知识）：analyze 产出 scope。
_BUILTIN_UNIT_CONTRACTS: dict[str, dict[str, list[str]]] = {
    "builtin.analyze": {"produces": ["scope"], "requires": []},
}


def _contract_of(decl: "PassDecl") -> dict[str, list[str]] | None:
    """单元契约（无声明 → None = 不参与校验，ADR-0015 §3 可选能力）。

    槽位级单元 → 承担它的 `slot_runner` 插件契约；
    插件单元 → 插件注册时的 produces/requires 声明（插件侧）；
    内置执行器 → 引擎内置契约（`_BUILTIN_UNIT_CONTRACTS`）。
    """
    if decl.plugin or decl.slot:
        from transform.engine import get_plugin_contracts

        qname = decl.plugin or "slot_runner"
        return get_plugin_contracts().get(qname)
    if decl.impl:
        return _BUILTIN_UNIT_CONTRACTS.get(decl.impl)
    return None


def _check_contract(decl: "PassDecl", available: set[str]) -> None:
    """时点边界契约校验（ADR-0015 §3）：requires 未满足 → fail-fast。

    校验点 = 单元执行前（阶段检查点，非消费闸）；produces 不在此并入——
    执行后按**物化登记**并入（`_collect_produced` / `_verify_produced`，
    阶段 7 切片 2：来源 = 本管线实际产出）。无契约声明 → 跳过。
    """
    contract = _contract_of(decl)
    if not contract:
        return
    missing = [r for r in contract.get("requires", []) if r not in available]
    if missing:
        raise ValueError(
            f"[pipeline] unit '{decl.name}' requires 未满足: {', '.join(missing)}"
            f"（应由该单元之前声明 produces 的单元提供；"
            f"当前可用: {', '.join(sorted(available)) or '(空)'}）"
        )


def _shapes_of(decl: "PassDecl") -> dict[str, dict] | None:
    """单元的形状声明（插件注册期 `shapes=`；槽位单元取 `slot_runner`）。"""
    if decl.plugin or decl.slot:
        from transform.engine import get_plugin_shapes

        qname = decl.plugin or "slot_runner"
        return get_plugin_shapes().get(qname)
    return None


def _collect_produced(decl: "PassDecl", state: "PassState") -> dict:
    """单元执行后的物化产物（名 → 对象，对象可为 None）。

    - 内置 analyze → `scope`（执行本身承接；None = 空分析，与既有
      "no scope produced" 警告语义一致，不升格 fail-fast）；
    - 插件/槽位单元 → 插件在 process 内经 `note_produced` 的登记；
    - 其余（builtin.transform / handler）→ 空，不参与契约。
    """
    if decl.impl == "builtin.analyze":
        return {"scope": state.scope}
    if (decl.plugin or decl.slot) and state.transformer is not None:
        return state.transformer.produced()
    return {}


def _verify_produced(
    decl: "PassDecl", contract: dict[str, list[str]] | None, produced: dict
) -> None:
    """执行后物化核验（阶段 7 切片 2）：声明须真产出，形状须合声明。

    - 真产出：声明的 produces 必须全部出现在物化登记中（缺 → fail-fast；
      未产出不得声明，声明不空转）；物化未声明的产物也 fail-fast
      （契约双向一致：声明 = 物化；无契约单元不受此限）；
    - 形状：单元可声明 `shapes`（`type`=dict/list、`non_empty`）——
      引擎机械核验对象（注册期已 fail-fast 校验 spec 合法性）。
    """
    if not contract:
        return
    declared = contract.get("produces", [])
    missing = [p for p in declared if p not in produced]
    if missing:
        raise ValueError(
            f"[pipeline] unit '{decl.name}' 声明的产物未物化: {', '.join(missing)}"
            f"（生产方须在 process 内经 note_produced 登记；未产出不得声明 produces）"
        )
    extra = sorted(p for p in produced if p not in declared)
    if extra:
        raise ValueError(
            f"[pipeline] unit '{decl.name}' 物化了未声明的产物: {', '.join(extra)}"
            f"（契约双向一致：声明 = 物化；补 produces 声明或不登记）"
        )
    for name, spec in (_shapes_of(decl) or {}).items():
        if name not in declared:
            continue  # 注册期已 fail-fast；此处防御
        obj = produced.get(name)
        want = spec.get("type")
        if want is not None and not isinstance(
            obj, dict if want == "dict" else list
        ):
            raise ValueError(
                f"[pipeline] unit '{decl.name}' 产物 '{name}' 形状不符: "
                f"声明 {want}，实得 {type(obj).__name__}"
            )
        if spec.get("non_empty") and not obj:
            raise ValueError(
                f"[pipeline] unit '{decl.name}' 产物 '{name}' 声明 non_empty，实为空"
            )


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
    state: "PassState",
    mapping_cfg: dict | None = None,
    plugin: str | None = None,
    slot: str | None = None,
    params: dict | None = None,
) -> None:
    """kind=transform pass：跑一轮 AstTransformer（消费 scope，None 跳过）。

    mapping_cfg 由调用方注入（_ensure_shared 按 rules_dir 缓存构建），
    不依赖全局 _loaded_components（可能被其他语言包污染）。
    slot 非空 → 只跑该槽位（槽位级单元，5b-3c-3）；
    plugin 非空（插件限定名）→ 只跑该插件（插件级单元，ADR-0015 §1），
    `params` 非空 → 作为插件**构造器关键字参数**实例化（5b-3b）；
    两者皆空 → 跑全部已注册插件（粗粒度，现行为）。
    """
    ctx = state.ctx
    # 本单元 transformer（跳过/未跑 = None，防上单元产物/自述残留）
    state.transformer = None
    if state.scope is None:
        ctx.log("[transform] skipped (no scope)")
        return
    AstTransformer.set_shared("rules", ctx.rules)
    AstTransformer.set_shared("mapping_cfg", mapping_cfg or {})
    if slot is not None:
        from transform.slot_runner import SlotRunnerPlugin

        transformer = AstTransformer(plugins=[SlotRunnerPlugin(only_slot=slot)])
    elif plugin is None:
        transformer = AstTransformer()
    else:
        from transform.engine import get_plugin_index

        cls = get_plugin_index().get(plugin)
        if cls is None:
            raise ValueError(f"[pipeline] 未知变换插件: {plugin!r}")
        try:
            instance = cls(**(params or {}))
        except TypeError as exc:
            raise ValueError(
                f"[pipeline] 插件 '{plugin}' 实例化失败"
                f"（params={params!r}）: {exc}"
            ) from exc
        transformer = AstTransformer(plugins=[instance])
    state.transformer = transformer

    # 一次 transform 完成：映射表构建 + 配置变换
    state.ast = transformer.transform(state.ast, state.scope)

    # 收集变换统计
    parts = []
    for plg in transformer.plugins:
        if hasattr(plg, "stats"):
            s = plg.stats
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
    available: set[str] = set()  # 已可用产物（契约校验，ADR-0015 §3）
    for index, decl in enumerate(schedules[schedule_name]):
        if decl.kind == "analyze" and not ctx.analyzer_enabled:
            ctx.log(f"[pipeline] pass '{decl.name}' skipped (analyze disabled)")
            continue
        if decl.kind == "transform" and not ctx.transform_enabled:
            ctx.log(f"[pipeline] pass '{decl.name}' skipped (transform disabled)")
            continue
        ctx.log(f"[pipeline] pass: {decl.name}")
        _check_contract(decl, available)
        _extra_before = set(state.extra)
        try:
            if decl.kind == "analyze":
                _run_pass_analyze(state)
            elif decl.kind == "transform":
                _run_pass_transform(
                    state, mapping_cfg, decl.plugin, decl.slot, decl.params
                )
            else:
                _run_pass_check(state, decl)
        except _ScheduleStop:
            state.trace.append(_trace_entry(index, decl, state, _extra_before))
            break
        # 执行后：物化核验（真产出 + 形状，阶段 7 切片 2）→ 产物并入可用集
        produced = _collect_produced(decl, state)
        _verify_produced(decl, _contract_of(decl), produced)
        if produced:
            available.update(produced)
        state.trace.append(
            _trace_entry(index, decl, state, _extra_before, produced)
        )
        if ctx.stage == decl.name:
            break
    # 单元执行轨迹（阶段 6 可视化）：谁在哪个时点跑了、向黑板（extra）写了哪些键。
    # 配对（分析→执行）隐式为设计，但**产物必须可视化**（ADR-0015 §2 硬要求）。
    ctx.result["trace"] = state.trace
    return state.ast, state.scope


def _trace_entry(
    index: int,
    decl: "PassDecl",
    state: "PassState",
    before: set,
    produced: dict | None = None,
) -> dict:
    """单元执行轨迹条目（时点 = index，按执行序）

    extra_added = 本次写入黑板（PassState.extra）的键；
    params     = 插件实例化参数（非空才带，5b-3b）；
    produced   = 本单元物化登记（非空才带，阶段 7）——按实际产出记录；
    artifacts  = 插件自述的中间产物/来源（transform 类，非空才带）——
                 同为实现 ADR-0015 §2「时点 = 可视化断点」。
    """
    entry = {
        "index": index,
        "name": decl.name,
        "kind": decl.kind,
        "extra_added": sorted(set(state.extra) - before),
        "extra_keys": sorted(state.extra),
    }
    if decl.impl:
        entry["impl"] = decl.impl
    if decl.params:
        entry["params"] = decl.params
    if produced:
        entry["produced"] = sorted(produced)
    if decl.kind == "transform" and state.transformer is not None:
        described = state.transformer.describe_plugins()
        if described:
            entry["artifacts"] = described
    return entry
