"""contract.py — 精化协议契约：项 / 定位 / 角色 / 能力面（语言包声明 → 引擎机械核验）。

引擎只做**文件操作**（读源 / 宏展开 / 解析 / AST 缓存 / 行映射）；"世界由哪些事实
构成"（端口有宽度、参数有值文本、信号有驱动/负载）是**语言知识** → 由语言包通过
既有能力机制声明（`[capabilities] elaborator = "file.py:fn"`，与 `formatter` /
`macro_policy` 同款，见 `core/component_protocol.md`）。

契约（引擎给事实、插件给求解）：

- **精化项列表**（可扩展；每项 = 一个可导出事实），字段见 `ITEM_KEYS`：
    `name`       项目名（容器键前缀；语言包作用域内唯一）
    `scope`      执行原子（引擎定义枚举：`file` / `unit` / `project`）
    `solver`     **求解的精化逻辑的函数名称**（加载期解析，缺失 → fail-fast）
    `provides`   本项负责的**容器键**（非空、跨项唯一）
    `depends_on` 项间依赖（引擎按**拓扑序**执行）
    `locator`    **如何从 AST 找到此类值**——声明式：在原子子树内按规则名匹配
    `locator_fn` 同上，但定位本身需要算法（函数名）
    `role`       引擎角色位（**引擎定义枚举**，见下）——只给"引擎自己要消费的产物"用
  `locator` / `locator_fn` **都可省略**：省略 = 求解器自行在原子子树内定位
  （P2 实测得出：`param_default` 的值分散在"头部 `#(..)` 字段"与"体内
  `ParamDeclStmt`"两种形态，单条规则名表达不了；而"怎么找"本身就是语言知识，
  归插件代码正是本协议的目的）。两者都给 → fail（语义歧义）。
- **求解函数**签名 `fn(hits, atom, ctx) -> Mapping | None`：返回本原子为 `provides`
  子集贡献的「容器键 → 值」；`None` = 本原子无此类值（合法）。
  省略定位时 `hits = [atom.node]`（原子根）。
- **产物容器** `context.extra[CTX_ELABORATION] = {容器键: {原子键: 值}}`——引擎只保证
  **容器与生命周期**，**条目名与值形状由语言包定义**（引擎不解释语义）。
- **角色位 `role`**：条目名由插件定 ⇒ 引擎无法按名寻址自己也要用的产物。`role` 是
  **引擎定义的封闭枚举**（同 `scope` 的性质，机制面）——声明了角色位的项，其**唯一**
  `provides` 键即该角色的容器键，引擎按角色取（见 `Elaborator.role_key`）。
  现役角色只有 `gen_activity`（generate 分支活性：`{文件路径: {id(节点): bool}}`，
  引擎侧消费方 = 层 3 的驱动过滤；层 3 迁入协议后此角色应随之退场）。
  ⚠ **角色位一律是过渡面**——终态下引擎不消费任何插件产物，故重构收口时 `ROLES`
  应为空（可机械检查）。
- 未声明能力 → 引擎**降级**（不提取、不注入容器）；声明非法 → fail-fast。

⚠ 与 `pipeline/schedule.py::_verify_produced`（声明 = 物化，双向一致）的**刻意差异**：
那里单元"全有或全无"，故"声明未产出"即缺陷；本处**按原子出产物**，"该原子无此类值"
是常态（无参数的模块本就没有 `param_default`），故不因"声明了但某原子无产物"报错——
只核验强方向（求解器返回了未声明的键 → fail）与跨项容器键唯一。

Doc: analyzer/elaboration/README.md
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.errors import ConfigError

# ── 执行原子（引擎定义枚举 = 机制面，可审计；同 ADR-0018 决策 2） ──
SCOPE_FILE = "file"
SCOPE_UNIT = "unit"
SCOPE_PROJECT = "project"
SCOPES: frozenset[str] = frozenset({SCOPE_FILE, SCOPE_UNIT, SCOPE_PROJECT})

# ── 引擎角色位（引擎定义枚举 = 机制面；只给"引擎自己要消费的产物"用） ──
# ⚠ 角色位**一律是过渡面**：终态（ADR-0019 决策 1）下引擎不消费任何插件产物，
#    故精化基座重构收口时 `ROLES` 应为空——这是"重构完成"的可机械检查判据。
#    每个角色**同时**定义寻址键与产物形状（引擎要消费它，与普通条目"形状归插件"不同）。
ROLE_GEN_ACTIVITY = "gen_activity"
"""generate 分支活性：寻址键 = **文件路径**；形状 = `{id(节点): bool}`。

bool = 该节点是否落在**选中**的 generate 分支内（层 3 据此"未选中分支的驱动不计"）。
引擎消费方 = `SignalGraphBuilder`；层 3 迁入协议（ADR-0019 P3-②）后**本角色退场**。
"""

ROLE_UNIT_PORTS = "unit_ports"
"""单元端口声明表：寻址键 = **单元名**；形状 = `{端口名: {name, direction, width_expr,
net_type, decl_node}}`。

引擎消费方 = `ConnectionElaborator`（层 2 按端口名/方向展开连接）+
`SignalGraphBuilder`（层 3 按方向判驱动/负载）。层 2/3 迁入协议（ADR-0019 P3-②）后
**本角色退场**——届时 ports 只在插件内部流通。
"""

ROLE_UNIT_CONNECTIONS = "unit_connections"
"""实例化点连接展开表（层 2）：寻址键 = **文件路径**；形状 =
`[{inst_name, module_name, inst_node, file, connects, ordered}]`。

引擎消费方 = `SignalGraphBuilder`（层 3 按连接记驱动/负载）+ `ProjectChecker` 注入
`context.extra["connections"]` 供 postpass（W104 等）。层 2/3 迁入协议后**本角色退场**。
"""

ROLES: frozenset[str] = frozenset(
    {ROLE_GEN_ACTIVITY, ROLE_UNIT_PORTS, ROLE_UNIT_CONNECTIONS}
)

# ── 声明键（未知键 fail-fast：拼错立刻可见，不静默忽略） ──
ITEM_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "scope",
        "locator",
        "locator_fn",
        "solver",
        "provides",
        "depends_on",
        "role",
    }
)
SPEC_KEYS: frozenset[str] = frozenset({"items", "solvers"})
LOCATOR_KEYS: frozenset[str] = frozenset({"rule"})


@dataclass(frozen=True)
class Locator:
    """声明式定位：在 scope 原子子树内按**规则名**匹配节点（先根序）。

    只认规则名——"怎么从匹配到的节点继续往下取值"是求解器（插件代码）的事；
    不在此发明字段投影小语言（那是"配置面膨胀"的老路，见 ADR-0019 权衡）。
    """

    rule: str


@dataclass(frozen=True)
class ElaborationItem:
    """一个精化项（= 一个可导出事实）。字段语义见模块头。"""

    name: str
    scope: str
    solver: str
    provides: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    locator: Locator | None = None
    locator_fn: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class ElaboratorSpec:
    """语言包声明的精化能力面（项列表 + 求解函数表）。

    `solvers` 同时承担 `locator_fn` 的解析（角色由项声明决定，不另立一张表）。
    """

    items: tuple[ElaborationItem, ...]
    solvers: Mapping[str, Callable[..., Any]]

    def order(self) -> tuple[ElaborationItem, ...]:
        """按 `depends_on` 拓扑序排列（同层保持声明序，结果确定；环 → fail-fast）。"""
        return _topo_order(self.items)

    def role_key(self, role: str) -> str | None:
        """该引擎角色位对应的容器键（无项声明该角色 → None）。"""
        for item in self.items:
            if item.role == role:
                return item.provides[0]
        return None


# ── 声明解析（fail-fast：任一处不合法直接报错，不静默降级） ──

def _topo_order(items: Sequence[ElaborationItem]) -> tuple[ElaborationItem, ...]:
    """Kahn 拓扑排序；同层按**声明序**（稳定，便于对拍与复现）。"""
    pending: dict[str, set[str]] = {it.name: set(it.depends_on) for it in items}
    by_name = {it.name: it for it in items}
    ordered: list[ElaborationItem] = []
    while pending:
        ready = [
            it.name for it in items if it.name in pending and not pending[it.name]
        ]
        if not ready:
            raise ConfigError(
                f"[elaborator] 精化项 depends_on 成环，无法定序: "
                f"{', '.join(sorted(pending))}"
            )
        for name in ready:
            ordered.append(by_name[name])
            del pending[name]
        for deps in pending.values():
            deps.difference_update(ready)
    return tuple(ordered)


def _as_mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(
            f"[elaborator] {what} 须为表，得到 {type(value).__name__}"
        )
    return value


def _reject_unknown(
    mapping: Mapping[str, Any], allowed: frozenset[str], what: str
) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ConfigError(
            f"[elaborator] {what} 含未知键: {', '.join(unknown)}"
            f"（支持 {', '.join(sorted(allowed))}）"
        )


def _name_tuple(
    value: Any, what: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    """非空字符串列表 → 元组（去重校验；None = 空）。"""
    if value is None:
        names: tuple[str, ...] = ()
    else:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(v, str) or not v for v in value
        ):
            raise ConfigError(
                f"[elaborator] {what} 须为非空字符串列表，得到 {value!r}"
            )
        names = tuple(value)
    if len(set(names)) != len(names):
        raise ConfigError(f"[elaborator] {what} 含重复项: {value!r}")
    if not allow_empty and not names:
        raise ConfigError(f"[elaborator] {what} 不得为空")
    return names


def _parse_locator(item: Mapping[str, Any], name: str, solvers: Mapping) -> tuple[
    Locator | None, str | None
]:
    """定位声明 → (`Locator` | None, `locator_fn` | None)；两者都给 → fail。"""
    locator, locator_fn = item.get("locator"), item.get("locator_fn")
    if locator is not None and locator_fn is not None:
        raise ConfigError(
            f"[elaborator] 精化项 '{name}' 不能同时声明 locator 与 locator_fn"
            f"（语义歧义；省略两者 = 求解器自行在原子子树内定位）"
        )
    if locator is None and locator_fn is None:
        return None, None
    if locator is not None:
        loc = _as_mapping(locator, f"精化项 '{name}' locator")
        _reject_unknown(loc, LOCATOR_KEYS, f"精化项 '{name}' locator")
        rule = loc.get("rule")
        if not isinstance(rule, str) or not rule:
            raise ConfigError(
                f"[elaborator] 精化项 '{name}' locator.rule 须为非空字符串，"
                f"得到 {rule!r}"
            )
        return Locator(rule=rule), None
    if not isinstance(locator_fn, str) or locator_fn not in solvers:
        raise ConfigError(
            f"[elaborator] 精化项 '{name}' locator_fn {locator_fn!r} 未在 solvers "
            f"中定义（已定义: {', '.join(sorted(solvers)) or '(空)'}）"
        )
    return None, locator_fn


def _parse_item(
    raw: Any, solvers: Mapping[str, Callable[..., Any]]
) -> ElaborationItem:
    item = _as_mapping(raw, "精化项")
    _reject_unknown(item, ITEM_KEYS, "精化项")

    name = item.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"[elaborator] 精化项 name 须为非空字符串，得到 {name!r}")

    scope = item.get("scope")
    if scope not in SCOPES:
        raise ConfigError(
            f"[elaborator] 精化项 '{name}' scope 须是 {sorted(SCOPES)} 之一，"
            f"得到 {scope!r}"
        )

    solver = item.get("solver")
    if not isinstance(solver, str) or solver not in solvers:
        raise ConfigError(
            f"[elaborator] 精化项 '{name}' solver {solver!r} 未在 solvers 中定义"
            f"（已定义: {', '.join(sorted(solvers)) or '(空)'}）"
        )

    provides = _name_tuple(
        item.get("provides"), f"精化项 '{name}' provides", allow_empty=False
    )
    depends_on = _name_tuple(item.get("depends_on"), f"精化项 '{name}' depends_on")
    if name in depends_on:
        raise ConfigError(f"[elaborator] 精化项 '{name}' depends_on 自引用")

    locator, locator_fn = _parse_locator(item, name, solvers)

    role = item.get("role")
    if role is not None:
        if role not in ROLES:
            raise ConfigError(
                f"[elaborator] 精化项 '{name}' role 须是引擎角色之一 "
                f"{sorted(ROLES)}，得到 {role!r}"
            )
        if len(provides) != 1:
            raise ConfigError(
                f"[elaborator] 精化项 '{name}' 声明了 role={role!r}，其 provides "
                f"须恰好一个键（引擎按角色取唯一产物），得到 {provides!r}"
            )
        # scope 不限：寻址键由**角色契约**定义（`gen_activity` = 文件路径），
        # 不是全局约束（原设 role ⇒ scope==unit 已放宽）。

    return ElaborationItem(
        name=name,
        scope=scope,
        solver=solver,
        provides=provides,
        depends_on=depends_on,
        locator=locator,
        locator_fn=locator_fn,
        role=role,
    )


def _reject_duplicate_provides(items: Sequence[ElaborationItem]) -> None:
    """容器键**跨项唯一**：两项写同一键 = 静默覆盖，直接拦下。"""
    owner: dict[str, str] = {}
    for it in items:
        for key in it.provides:
            prev = owner.get(key)
            if prev is not None:
                raise ConfigError(
                    f"[elaborator] 容器键 '{key}' 被多项声明: '{prev}' 与 "
                    f"'{it.name}'（同一键只能有一个产出方）"
                )
            owner[key] = it.name


def _reject_duplicate_roles(items: Sequence[ElaborationItem]) -> None:
    """引擎角色位跨项唯一：两个项应答同一角色 → 引擎按角色取值就有歧义。"""
    owner: dict[str, str] = {}
    for it in items:
        if it.role is None:
            continue
        prev = owner.get(it.role)
        if prev is not None:
            raise ConfigError(
                f"[elaborator] 引擎角色 '{it.role}' 被多项声明: '{prev}' 与 "
                f"'{it.name}'"
            )
        owner[it.role] = it.name


def parse_spec(raw: Any) -> ElaboratorSpec:
    """能力入口返回值 → `ElaboratorSpec`（fail-fast：任一处不合法即报错）。

    加载期一并完成**环探测**（`order()`）——不留到运行期才发现定序失败。
    """
    spec = _as_mapping(raw, "elaborator 能力入口返回值")
    _reject_unknown(spec, SPEC_KEYS, "elaborator 能力入口返回值")

    solvers = _as_mapping(spec.get("solvers"), "elaborator solvers")
    not_callable = sorted(k for k, v in solvers.items() if not callable(v))
    if not_callable:
        raise ConfigError(
            f"[elaborator] solvers 项须可调用: {', '.join(not_callable)}"
        )

    raw_items = spec.get("items")
    if not isinstance(raw_items, (list, tuple)) or not raw_items:
        raise ConfigError(
            f"[elaborator] items 须为非空列表，得到 {type(raw_items).__name__}"
        )

    items = tuple(_parse_item(r, solvers) for r in raw_items)
    names = [it.name for it in items]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise ConfigError(f"[elaborator] 精化项重名: {', '.join(dup)}")

    known = set(names)
    for it in items:
        missing = [d for d in it.depends_on if d not in known]
        if missing:
            raise ConfigError(
                f"[elaborator] 精化项 '{it.name}' depends_on 引用了未声明的项: "
                f"{', '.join(missing)}"
            )

    _reject_duplicate_provides(items)
    _reject_duplicate_roles(items)
    result = ElaboratorSpec(items=items, solvers=dict(solvers))
    result.order()  # 环探测（加载期 fail-fast）
    return result
