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
from typing import Any, Callable, cast

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
    # 单元产物通道（契约名 → 对象，ADR-0015 §3）：从已跑单元的物化登记累积；
    # 经 `AstTransformer.set_shared("productions", ...)` 供后续单元消费
    # （故消费方不必与生产方同实例——插件级单元的数据路径与契约声明一致）。
    productions: dict = field(default_factory=dict)
    # 单元执行轨迹（阶段 6 可视化：时点 = 可视化断点）——每单元一条
    # {index, name, kind, impl?, slot?, params?, produced?, extra_added,
    #  extra_keys, artifacts?}
    trace: list[dict] = field(default_factory=list)


def _entry_fields(e, schedule_name: str) -> tuple[str, int | None, str | None]:
    """条目 → (name, order, after)；形态非法 / order 与 after 并存 → ValueError。"""
    if isinstance(e, str):
        return e, None, None
    if not isinstance(e, dict):
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 条目形态非法: {e!r}"
        )
    name = e.get("name")
    order = e.get("order")
    after = e.get("after")
    if order is not None and after is not None:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 条目 {name!r} "
            f"order 与 after 互斥"
        )
    # order/after 的合法性由 `_check_order` 与调用方校验（此处只收类型，不改行为）
    return cast(str, name), cast(int | None, order), cast(str | None, after)


def _check_order(order, schedule_name: str) -> None:
    """order 须为非负整数（bool 也算非法——True/False 会静默变成 1/0）。"""
    if order is None:
        return
    if not isinstance(order, int) or isinstance(order, bool) or order < 0:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' order 须为非负整数: {order!r}"
        )


def _validate_entry(
    name,
    order,
    after,
    schedule_name: str,
    valid_names: set[str],
    seen: set[str],
) -> None:
    """单条目的声明面校验：名字已声明且不重复 / order 合法 / after 已声明。"""
    if not isinstance(name, str) or name not in valid_names:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 引用未声明的 pass: {name!r}"
        )
    if name in seen:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 重复引用 pass: {name}"
        )
    seen.add(name)
    _check_order(order, schedule_name)
    if after is not None and after not in valid_names:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' after 引用未声明的 pass: {after!r}"
        )


def _normalize_entries(
    entries: list, schedule_name: str, valid_names: set[str]
) -> list[dict]:
    """schedule 条目 → 规范化 {name, order, after}（逐条目校验，fail-fast）。"""
    norm: list[dict] = []
    seen_names: set[str] = set()
    for e in entries:
        name, order, after = _entry_fields(e, schedule_name)
        _validate_entry(name, order, after, schedule_name, valid_names, seen_names)
        norm.append({"name": name, "order": order, "after": after})
    return norm


def _claim_slot(slot_of: dict[str, int], name: str, s: int, schedule_name: str) -> None:
    """占槽；已被占用 → 时点冲突（需用 order 或 after 分前后）。"""
    if s in slot_of.values():
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 时点冲突: "
            f"pass '{name}' 落 slot {s}（已被占用），"
            f"需用 order 或 after 分前后"
        )
    slot_of[name] = s


def _pin_explicit_orders(
    norm: list[dict], slot_of: dict[str, int], schedule_name: str
) -> None:
    """1. 显式 order 钉号。"""
    for e in norm:
        if e["order"] is not None:
            _claim_slot(slot_of, e["name"], e["order"], schedule_name)


def _fill_by_declaration_order(
    norm: list[dict], slot_of: dict[str, int], schedule_name: str
) -> list[dict]:
    """2. 声明序走查：默认条目填空下一个空闲 slot（跳过已钉号），after 目标已知
    则即时落 slot(after)+1。

    返回仍待解析的 after 条目（其目标尚未落位）。
    """
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
            _claim_slot(slot_of, e["name"], slot_of[e["after"]] + 1, schedule_name)
        else:
            deferred.append(e)
    return deferred


def _resolve_deferred(
    deferred: list[dict], slot_of: dict[str, int], schedule_name: str
) -> None:
    """3. 迭代解析剩余 after 条目直至不动点；无法推进即 after 环（报错）。"""
    while deferred:
        progressed = False
        for e in list(deferred):
            if e["after"] in slot_of:
                _claim_slot(slot_of, e["name"], slot_of[e["after"]] + 1, schedule_name)
                deferred.remove(e)
                progressed = True
        if not progressed:
            chain = " -> ".join(sorted(e["name"] for e in deferred))
            raise ValueError(
                f"[pipeline] schedule '{schedule_name}' after 环: {chain}"
            )


def _sequence_entries(
    entries: list, schedule_name: str, valid_names: set[str]
) -> list[str]:
    """时点序列器：把 schedule 的 passes 条目解析为有序 pass 名列表。

    条目形态：str（名字）或 dict（name + order | after，二者互斥）。
    slot 推导（三步）：
        1. order = N 显式钉号（互相冲突报错）        → `_pin_explicit_orders`
        2. 按声明序走查：默认条目填空下一个空闲 slot（跳过已钉号）；
           after 条目目标已知则立即落 slot(target)+1  → `_fill_by_declaration_order`
        3. 剩余 after 条目迭代解析，直至不动点；
           仍有未解析 → after 环（报错）              → `_resolve_deferred`
    冲突检测：两个条目落同一 slot → ValueError（"需分前后"）。
    """
    norm = _normalize_entries(entries, schedule_name, valid_names)
    slot_of: dict[str, int] = {}
    _pin_explicit_orders(norm, slot_of, schedule_name)
    deferred = _fill_by_declaration_order(norm, slot_of, schedule_name)
    _resolve_deferred(deferred, slot_of, schedule_name)
    by_slot = {s: n for n, s in slot_of.items()}
    return [by_slot[s] for s in sorted(by_slot)]


def _merge_pass_decls() -> dict[str, dict]:
    """pass 声明：内置 + 插件（重名 fail-fast）。"""
    pass_decls: dict[str, dict] = dict(BUILTIN_PASSES)
    for name, decl in get_pipeline_pass_decls().items():
        if name in pass_decls:
            raise ValueError(
                f"[pipeline] pass 名 '{name}' 与内置/已声明 pass 冲突"
            )
        pass_decls[name] = decl
    return pass_decls


def _make_pass_decl(name: str, decl: dict) -> PassDecl:
    """单 pass 声明 → PassDecl。

    kind 须合法，check 类须带 handler。内置 pass 填 impl（= 内置执行器引用）→
    trace 可见 + 契约校验可查；插件 pass 声明里给了 impl 则沿用（契约同样生效）。
    """
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
    impl = decl.get("impl") or (
        f"builtin.{name}" if name in BUILTIN_PASSES else None
    )
    return PassDecl(name=name, kind=kind, handler=handler, impl=impl)


def _resolve_pass_decls(pass_decls: dict[str, dict]) -> dict[str, PassDecl]:
    """逐 pass 校验并解析为 PassDecl。"""
    return {name: _make_pass_decl(name, decl) for name, decl in pass_decls.items()}


def _build_declared_schedule(
    entries: list, sname: str, resolved: dict[str, PassDecl]
) -> list[PassDecl]:
    """一条 schedule 声明 → 有序 PassDecl 列表（时点序列化）。"""
    ordered = _sequence_entries(entries, sname, set(resolved))
    return [resolved[n] for n in ordered]


def build_schedules() -> dict[str, list[PassDecl]]:
    """构建全部 schedule：内置缺省 + 插件声明（经 plugin_loader 合并）。

    返回 {schedule 名: [PassDecl 执行序]}。无任何声明时仅含
    default = [analyze, transform]（现行为）。
    """
    resolved = _resolve_pass_decls(_merge_pass_decls())
    schedules = {
        sname: _build_declared_schedule(sdecl.get("passes", []), sname, resolved)
        for sname, sdecl in get_pipeline_schedules().items()
    }
    # 缺省 schedule（未声明时 = 现行为）
    if DEFAULT_SCHEDULE_NAME not in schedules:
        schedules[DEFAULT_SCHEDULE_NAME] = _build_declared_schedule(
            DEFAULT_SCHEDULE_ENTRIES, DEFAULT_SCHEDULE_NAME, resolved
        )
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

def _slot_unit_decl(u, slot_decls: dict) -> "PassDecl":
    """槽位级单元（5b-3c-3）：只跑该槽位（引擎 slot_runner 单槽位执行）。

    校验：限 transform / 不支持 params（运行器固定单槽位执行，无实例化参数）/
    槽位须已声明。
    """
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
    return PassDecl(name=u.name, kind=u.type, slot=u.slot, impl=f"slot:{u.slot}")


def _plugin_unit_decl(u, plugin_index: dict) -> "PassDecl":
    """插件级单元：只跑该插件（可带构造器 params，签名核验 fail-fast）。

    语言作用域：单元声明按语言包，不得引用**别的语言**的插件（插件注册表
    进程级累积，名字解析本身不区分语言）。
    """
    from transform.engine import active_plugin_classes

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
    cls = plugin_index[u.impl]
    if cls not in active_plugin_classes():
        raise ValueError(
            f"[pipeline] unit '{u.name}' 的插件 {u.impl!r} 不在当前语言"
            f"作用域（单元声明按语言包，不得引用别的语言的插件）"
        )
    if u.params:
        _validate_plugin_params(u.name, u.impl, cls, u.params)
    return PassDecl(
        name=u.name, kind=u.type, plugin=u.impl, impl=u.impl, params=u.params
    )


def _builtin_unit_decl(u, handler) -> "PassDecl":
    """内置执行器 / 文件处理器单元：params 不支持（实例化参数覆写仅插件单元）。"""
    from .units import BUILTIN_IMPLS

    if u.impl not in BUILTIN_IMPLS and handler is None:
        raise ValueError(
            f"[pipeline] unit '{u.name}' impl 未解析为 handler: {u.impl!r}"
        )
    if u.params:
        raise ValueError(
            f"[pipeline] unit '{u.name}' 内置/处理器单元不支持 params"
            f"（实例化参数覆写仅插件单元）"
        )
    return PassDecl(name=u.name, kind=u.type, handler=handler, impl=u.impl)


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
        if u.slot:
            out.append(_slot_unit_decl(u, slot_decls))
            continue
        if classify_impl(u.impl) == IMPL_PLUGIN:
            out.append(_plugin_unit_decl(u, plugin_index))
            continue
        decl = unit_decls.get(u.name) or {}
        out.append(_builtin_unit_decl(u, decl.get("_handler")))
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


def _verify_materialized(decl: "PassDecl", declared: list[str], produced: dict) -> None:
    """契约双向一致：声明的 produces 须全部物化；物化了未声明的产物也报错。"""
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


def _verify_shape(
    decl: "PassDecl", name: str, spec: dict, declared: list[str], produced: dict
) -> None:
    """单产物形状核验：`type`=dict/list、`non_empty`（注册期已校验 spec 合法性）。"""
    if name not in declared:
        return  # 注册期已 fail-fast；此处防御
    obj = produced.get(name)
    want = spec.get("type")
    if want is not None and not isinstance(obj, dict if want == "dict" else list):
        raise ValueError(
            f"[pipeline] unit '{decl.name}' 产物 '{name}' 形状不符: "
            f"声明 {want}，实得 {type(obj).__name__}"
        )
    if spec.get("non_empty") and not obj:
        raise ValueError(
            f"[pipeline] unit '{decl.name}' 产物 '{name}' 声明 non_empty，实为空"
        )


def _verify_produced(
    decl: "PassDecl", contract: dict[str, list[str]] | None, produced: dict
) -> None:
    """执行后物化核验（阶段 7 切片 2）：声明须真产出，形状须合声明。

    - 真产出：声明的 produces 必须全部出现在物化登记中（缺 → fail-fast；
      未产出不得声明，声明不空转）；物化未声明的产物也 fail-fast
      （契约双向一致：声明 = 物化；无契约单元不受此限）——见 `_verify_materialized`；
    - 形状：单元可声明 `shapes`（`type`=dict/list、`non_empty`）——
      引擎机械核验对象（见 `_verify_shape`）。
    """
    if not contract:
        return
    declared = contract.get("produces", [])
    _verify_materialized(decl, declared, produced)
    for name, spec in (_shapes_of(decl) or {}).items():
        _verify_shape(decl, name, spec, declared, produced)


class _ScheduleStop(Exception):
    """内部控制流：pass 请求终止调度（analyze 报 error 级诊断）。"""


def _dump_analyze_artifacts(ctx, analyzer) -> None:
    """符号表 / 变换回调转储（非 quiet 时）。

    Dump transform callbacks (_ref_callbacks) to trans_callback/ —— 经能力查找
    （P2.5）接入：typed_ports 声明 `[capabilities] transform_callbacks`；其他
    语言无此能力时 get_capability 返回 None，回调收集降级为空。
    """
    if ctx.quiet:
        return
    if ctx.sym_json:
        save_json(
            analyzer.root_scope.to_dict(), ctx.sym_json, "symbols",
            log_fn=ctx.log
        )
    collect_cbs = get_capability("transform_callbacks")
    callbacks = collect_cbs(analyzer.root_scope) if collect_cbs else {}
    if callbacks and ctx.cb_json:
        save_json(callbacks, ctx.cb_json, "callbacks", log_fn=ctx.log)


def _raise_on_analyze_errors(ctx, analyzer) -> None:
    """error 级诊断 → 置 ctx.result["error"] 并抛 _ScheduleStop（停调度停管线）。"""
    if not analyzer.has_errors:
        return
    for d in analyzer.diagnostics:
        ctx.log(f"[analyzer] {d}")
    if any(d.level == "error" for d in analyzer.diagnostics):
        ctx.result["error"] = "; ".join(
            str(d) for d in analyzer.diagnostics if d.level == "error"
        )
        ctx.log("[analyzer] semantic errors, stopping pipeline")
        raise _ScheduleStop()


def _run_pass_analyze(state: "PassState") -> None:
    """kind=analyze pass：跑一轮 AnalysisTraversal，覆盖 scope。

    error 级诊断 → 置 ctx.result["error"] 并抛 _ScheduleStop（见
    `_raise_on_analyze_errors`）。
    """
    ctx = state.ctx
    analyzer = AnalysisTraversal(ctx.rules)
    state.ast = analyzer.analyze(state.ast)
    state.analyzer = analyzer
    state.scope = analyzer.root_scope
    if analyzer.root_scope is None:
        ctx.log("[analyzer] warning: no scope produced")
    else:
        _dump_analyze_artifacts(ctx, analyzer)
        ctx.log(f"[symbols] {len(analyzer.all_symbols)} symbols")
    _raise_on_analyze_errors(ctx, analyzer)


def _make_transformer(plugin: str | None, slot: str | None, params: dict | None):
    """按单元形态建 transformer。

    slot 非空 → 只跑该槽位（槽位级单元，5b-3c-3）；
    plugin 非空（插件限定名）→ 只跑该插件（插件级单元，ADR-0015 §1），
    `params` 非空 → 作为插件**构造器关键字参数**实例化（5b-3b）；
    两者皆空 → 跑全部已注册插件（粗粒度，现行为）。
    """
    if slot is not None:
        from transform.slot_runner import SlotRunnerPlugin

        return AstTransformer(plugins=[SlotRunnerPlugin(only_slot=slot)])
    if plugin is None:
        return AstTransformer()
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
    return AstTransformer(plugins=[instance])


def _log_transform_stats(ctx, transformer) -> None:
    """变换统计一行（`[transform] k=v ...`；插件可自述 stats）。"""
    parts = []
    for plg in transformer.plugins:
        stats = getattr(plg, "stats", None)
        if stats is None:
            continue
        for k, v in stats.items():
            if v:
                parts.append(f"{k}={v}")
    if parts:
        ctx.log(f"[transform] {' '.join(parts)}")


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
    单插件/槽位选择与参数实例化见 `_make_transformer`。
    """
    ctx = state.ctx
    # 本单元 transformer（跳过/未跑 = None，防上单元产物/自述残留）
    state.transformer = None
    if state.scope is None:
        ctx.log("[transform] skipped (no scope)")
        return
    AstTransformer.set_shared("rules", ctx.rules)
    AstTransformer.set_shared("mapping_cfg", mapping_cfg or {})
    # 产物通道：已跑单元的物化登记（按契约名消费，跨 transformer 实例可见）
    AstTransformer.set_shared("productions", state.productions)
    transformer = _make_transformer(plugin, slot, params)
    state.transformer = transformer

    # 一次 transform 完成：映射表构建 + 配置变换
    state.ast = transformer.transform(state.ast, state.scope)
    _log_transform_stats(ctx, transformer)


def _run_pass_check(state: "PassState", decl: "PassDecl") -> None:
    """kind=check pass：执行插件 handler（fn(state) -> None）。

    语义：检查/验证/外部工具挂载（不改 AST，可读改 scope/extra 产诊断）。
    """
    assert decl.handler is not None
    decl.handler(state)


_LEGACY_PASS_STAGES = ("analyze", "transform")


def _is_runnable(state: "PassState", decl: "PassDecl") -> bool:
    """单元是否具备执行输入（transform 需要 scope；无输入由执行层按既有语义跳过）。"""
    return not (decl.kind == "transform" and state.scope is None)


def _skip_by_switch(ctx: Any, decl: "PassDecl") -> bool:
    """开关过滤：analyzer_enabled=False 滤 kind=analyze；transform_enabled 同理。"""
    if decl.kind == "analyze" and not ctx.analyzer_enabled:
        ctx.log(f"[pipeline] pass '{decl.name}' skipped (analyze disabled)")
        return True
    if decl.kind == "transform" and not ctx.transform_enabled:
        ctx.log(f"[pipeline] pass '{decl.name}' skipped (transform disabled)")
        return True
    return False


def _dispatch_unit(state: "PassState", decl: "PassDecl", mapping_cfg: dict | None) -> None:
    """按 kind 分派执行单元。"""
    if decl.kind == "analyze":
        _run_pass_analyze(state)
    elif decl.kind == "transform":
        _run_pass_transform(state, mapping_cfg, decl.plugin, decl.slot, decl.params)
    else:
        _run_pass_check(state, decl)


def _finalize_unit(decl: "PassDecl", state: "PassState", available: set[str]) -> dict:
    """执行后：物化核验（真产出 + 形状，阶段 7 切片 2）→ 产物并入可用集。"""
    produced = _collect_produced(decl, state)
    _verify_produced(decl, _contract_of(decl), produced)
    if produced:
        available.update(produced)
        state.productions.update(produced)
    return produced


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
    - 开关过滤：见 `_skip_by_switch`。
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
        if _skip_by_switch(ctx, decl):
            continue
        ctx.log(f"[pipeline] pass: {decl.name}")
        # 契约校验/物化核验只在单元**实际会执行**时进行：上游被开关关掉 /
        # analyze 未产出 scope 时，transform 单元无输入 → 由执行层按既有语义
        # 跳过（log），不报"requires 未满足/产物未物化"——那是配置错误
        # （顺序/引用），与开关无关。
        runnable = _is_runnable(state, decl)
        if runnable:
            _check_contract(decl, available)
        _extra_before = set(state.extra)
        try:
            _dispatch_unit(state, decl, mapping_cfg)
        except _ScheduleStop:
            state.trace.append(_trace_entry(index, decl, state, _extra_before))
            break
        # 执行后：物化核验 → 产物并入可用集
        produced: dict = {}
        if runnable:
            produced = _finalize_unit(decl, state, available)
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
    requires   = 单元声明的 requires（非空才带，阶段 7）——报告侧画依赖链；
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
    contract = _contract_of(decl)
    if contract and contract.get("requires"):
        entry["requires"] = list(contract["requires"])
    if produced:
        entry["produced"] = sorted(produced)
    if decl.kind == "transform" and state.transformer is not None:
        described = state.transformer.describe_plugins()
        if described:
            entry["artifacts"] = described
    if decl.kind == "analyze" and state.analyzer is not None:
        # postpass 链也是时点：哪一环跑了、报了几条诊断（链内契约见
        # analyzer/traversal.py::_run_postpasses）
        postpasses = getattr(state.analyzer, "postpass_trace", None)
        if postpasses:
            entry["artifacts"] = {"postpasses": list(postpasses)}
    return entry
