"""精化协议（`analyzer/elaboration/`）——契约 / 驱动器 / 降级，纯单元测试。

组别归属：analyzer（精化协议面）。本文件守 ADR-0019 的**机制面**：

1. 声明解析全字段 fail-fast（未知键 / 重名 / 容器键跨项重复 / 依赖成环与自引用 /
   定位二选一 / 求解名未解析）；
2. 拓扑序执行（`depends_on` 决定先后，同层保持声明序）；
3. 驱动器：原子枚举 → 声明式定位（规则名）→ 求解 → 按声明的容器键归位；
4. 核验只做**强方向**（返回未声明的键 → fail）；"某原子无此类值"合法（容器键预置）；
5. 未声明能力 → 降级（不枚举原子、不写容器，零副作用）。

⚠ P1 阶段本包**未接线**（无语言包声明 `elaborator`），故此处全用替身；真实语言包的
正例自 P2 起（届时本文件顶部"降级"一条要按实际声明改写）。
"""

from __future__ import annotations

import pytest

from core._protocol import CTX_ELABORATION
from core.define import Node
from core.errors import ConfigError

from analyzer.elaboration import (
    ROLES,
    SCOPE_FILE,
    SCOPE_UNIT,
    Atom,
    Elaborator,
    ElaboratorSpec,
    load_elaborator_spec,
    parse_spec,
)
from analyzer.elaboration.contract import Locator


# ── 替身 ──

def _noop(*_args, **_kwargs):
    return None


class _Source:
    """原子供源替身：按 scope 给固定原子，并记录被问过的 scope。"""

    def __init__(self, **by_scope):
        self._by_scope = by_scope
        self.calls: list[str] = []

    def atoms(self, scope):
        self.calls.append(scope)
        return list(self._by_scope.get(scope, ()))


def _item(**over) -> dict:
    base = {
        "name": "x",
        "scope": SCOPE_FILE,
        "locator": {"rule": "R"},
        "solver": "solve",
        "provides": ["x"],
    }
    base.update(over)
    return base


def _spec(items, solvers=None) -> dict:
    return {"items": items, "solvers": solvers or {"solve": _noop}}


def _root_with(*names: str) -> Node:
    root = Node("Root")
    for n in names:
        root.add_sub_node(Node(n))
    return root


# ── 1. 声明解析：形状与 fail-fast ──

def test_parse_minimal_spec():
    spec = parse_spec(_spec([_item()]))
    assert isinstance(spec, ElaboratorSpec)
    assert spec.items[0].locator == Locator(rule="R")
    assert spec.items[0].provides == ("x",)
    assert spec.items[0].depends_on == ()


@pytest.mark.parametrize(
    "bad",
    [
        5,  # 非表
        {"items": [], "solvers": {}},  # items 为空
        {"items": [_item()]},  # 缺 solvers
        {"items": [_item()], "solvers": {"solve": 1}},  # solver 不可调用
        {"items": [_item()], "solvers": {"solve": _noop}, "extra": 1},  # 顶层未知键
    ],
)
def test_malformed_spec_shapes_fail_fast(bad):
    with pytest.raises(ConfigError):
        parse_spec(bad)


@pytest.mark.parametrize(
    "bad_item",
    [
        _item(bogus=1),  # 项未知键
        _item(locator={"rule": "R", "fields": {}}),  # locator 未知键（不造投影小语言）
        _item(name=""),  # 项名空
        _item(scope="module"),  # scope 非引擎枚举
        _item(solver="missing"),  # 求解名未解析
        _item(provides=[]),  # provides 空
        _item(provides=["a", "a"]),  # provides 项内重复
        _item(depends_on=["ghost"]),  # 依赖未声明的项
        _item(name="a", depends_on=["a"]),  # 自引用
        _item(locator={"rule": "R"}, locator_fn="solve"),  # 定位两给（语义歧义）
        _item(locator={"rule": ""}),  # 规则名空
        _item(role="not_a_role"),  # 引擎角色位非法
        _item(role="gen_activity", provides=["a", "b"]),  # 终态下任何 role 非法
    ],
)
def test_malformed_item_fails_fast(bad_item):
    with pytest.raises(ConfigError):
        parse_spec(_spec([bad_item]))


def test_duplicate_item_names_fail_fast():
    items = [
        _item(name="dup", provides=["ka"]),
        _item(name="dup", provides=["kb"]),
    ]
    with pytest.raises(ConfigError, match="重名"):
        parse_spec(_spec(items))


def test_container_key_unique_across_items():
    """两项写同一容器键 = 静默覆盖 → 拦下。"""
    items = [
        _item(name="i1", provides=["k"]),
        _item(name="i2", provides=["k"]),
    ]
    with pytest.raises(ConfigError, match="只能有一个产出方"):
        parse_spec(_spec(items))


def test_roles_are_empty_at_terminal_state():
    """**终态判据**：`ROLES` 为空 → 任何 role 声明都被拒。

    角色位是"引擎消费插件产物"的寻址机制；P3 收口后引擎不消费任何产物，故没有合法
    角色——这是"角色位一律是过渡面"的可机械检查后果（引擎不解释语义 ⇔ 无需按名寻址）。
    """
    assert ROLES == frozenset(), f"ROLES 应为空（终态判据），实得 {sorted(ROLES)}"
    with pytest.raises(ConfigError, match="引擎角色"):
        parse_spec(_spec([_item(role="gen_activity", scope=SCOPE_FILE)]))


def test_role_key_none_when_role_not_declared():
    spec = parse_spec(_spec([_item()]))
    assert spec.role_key("unit_constants") is None
    assert spec.role_key("gen_activity") is None


def test_duplicate_role_across_items_rejected():
    """两个项应答同一角色 → 引擎按角色取值有歧义。"""
    items = [
        _item(name="i1", provides=["ka"], role="gen_activity"),
        _item(name="i2", provides=["kb"], role="gen_activity"),
    ]
    with pytest.raises(ConfigError, match="引擎角色"):
        parse_spec(_spec(items))


def test_depends_on_cycle_fails_at_load_time():
    """环在**加载期**就报（不留到运行期才发现定不了序）。"""
    items = [
        _item(name="a", provides=["ka"], depends_on=["b"]),
        _item(name="b", provides=["kb"], depends_on=["a"]),
    ]
    with pytest.raises(ConfigError, match="成环"):
        parse_spec(_spec(items))


def test_locator_fn_resolves_in_same_solver_table():
    spec = parse_spec(
        _spec(
            [_item(locator=None, locator_fn="loc")],
            solvers={"solve": _noop, "loc": _noop},
        )
    )
    assert spec.items[0].locator is None
    assert spec.items[0].locator_fn == "loc"


def test_locator_fn_unresolved_fails_fast():
    with pytest.raises(ConfigError, match="locator_fn"):
        parse_spec(_spec([_item(locator=None, locator_fn="missing")]))


# ── 2. 拓扑序 ──

def test_order_follows_depends_on_and_keeps_declaration_order():
    """被依赖项先跑；无依赖关系的同层项保持**声明序**（结果确定可复现）。"""
    items = [
        _item(name="c", provides=["kc"], depends_on=["a"]),
        _item(name="b", provides=["kb"]),
        _item(name="a", provides=["ka"]),
    ]
    order = [it.name for it in parse_spec(_spec(items)).order()]
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("a")  # b 声明在 a 前 → 同层按声明序


# ── 3. 驱动器：定位 / 归位 / 容器 ──

def test_driver_locates_by_rule_and_fills_container():
    root = _root_with("Other", "R")
    seen: list[list[str]] = []

    def solve(hits, atom, ctx):
        seen.append([n.node_name for n in hits])
        return {"x": "v"}

    spec = parse_spec(_spec([_item()], solvers={"solve": solve}))
    source = _Source(file=[Atom(key="a.v", path="a.v", node=root)])
    extra: dict = {}
    result = Elaborator(spec).run(source, extra)

    assert seen == [["R"]]  # 只收规则名命中的节点
    assert extra[CTX_ELABORATION] == {"x": {"a.v": "v"}}
    assert result.products == {"x": {"a.v": "v"}}
    assert result.ran == ("x",)


def test_driver_dispatches_by_scope_and_keys_by_atom():
    def solve(hits, atom, ctx):
        return {"x": atom.key}

    spec = parse_spec(_spec([_item(scope=SCOPE_UNIT)], solvers={"solve": solve}))
    source = _Source(
        unit=[Atom(key="top.u1", node=Node("Root")), Atom(key="top.u2", node=Node("Root"))]
    )
    extra: dict = {}
    Elaborator(spec).run(source, extra)

    assert extra[CTX_ELABORATION]["x"] == {"top.u1": "top.u1", "top.u2": "top.u2"}
    assert source.calls == [SCOPE_UNIT]  # 只问声明的 scope


def test_atom_key_conflict_first_wins():
    """同一原子键出现两份产物 → **取先**（与引擎单元索引"首个定义者优先"同口径）。

    同名单元在多个文件重复定义时，若产物"后写覆盖"，引擎按单元名取产物就会取到**另一个
    文件**的值（端口表/参数表错配 → 跨文件检查静默错判）。
    """

    def solve(hits, atom, ctx):
        return {"x": atom.path}  # 值 = 文件路径，便于分辨哪一份胜出

    spec = parse_spec(_spec([_item(scope=SCOPE_UNIT)], solvers={"solve": solve}))
    source = _Source(
        unit=[
            Atom(key="dup", path="a.v", node=Node("Root")),
            Atom(key="dup", path="b.v", node=Node("Root")),
        ]
    )
    extra: dict = {}
    Elaborator(spec).run(source, extra)
    assert extra[CTX_ELABORATION]["x"] == {"dup": "a.v"}, "原子键冲突应取先"


def test_container_preseeded_even_when_atom_yields_nothing():
    """声明了但某原子无此类值 → 键仍在（空表），下游不必两套写法。"""
    spec = parse_spec(_spec([_item()], solvers={"solve": _noop}))
    extra: dict = {}
    result = Elaborator(spec).run(
        _Source(file=[Atom(key="a.v", node=Node("Root"))]), extra
    )
    assert extra[CTX_ELABORATION] == {"x": {}}
    assert result.ran == ("x",)  # 项跑了，只是没产物


def test_later_item_reads_earlier_products_through_ctx():
    """`depends_on` 的真实用途：后声明项经 `ctx.products` 读先声明项的产物。"""

    def solve_a(hits, atom, ctx):
        return {"ka": 1}

    def solve_b(hits, atom, ctx):
        return {"kb": ctx.products["ka"]["a.v"] + 1}

    items = [
        _item(name="a", provides=["ka"], solver="sa"),
        _item(name="b", provides=["kb"], solver="sb", depends_on=["a"]),
    ]
    spec = parse_spec(_spec(items, solvers={"sa": solve_a, "sb": solve_b}))
    extra: dict = {}
    Elaborator(spec).run(_Source(file=[Atom(key="a.v", node=Node("Root"))]), extra)
    assert extra[CTX_ELABORATION]["kb"] == {"a.v": 2}


def test_locator_fn_used_when_declared():
    def loc(atom, ctx):
        return [Node("R"), Node("R")]

    def solve(hits, atom, ctx):
        return {"x": len(hits)}

    spec = parse_spec(
        _spec([_item(locator=None, locator_fn="loc")], solvers={"solve": solve, "loc": loc})
    )
    extra: dict = {}
    Elaborator(spec).run(_Source(file=[Atom(key="a.v", node=Node("Root"))]), extra)
    assert extra[CTX_ELABORATION]["x"] == {"a.v": 2}


def test_atom_without_node_yields_no_hits():
    """定位起点为空（工程级原子）→ 无命中，不炸。"""

    def solve(hits, atom, ctx):
        return {"x": len(hits)}

    spec = parse_spec(_spec([_item()], solvers={"solve": solve}))
    extra: dict = {}
    Elaborator(spec).run(_Source(file=[Atom(key="a.v", node=None)]), extra)
    assert extra[CTX_ELABORATION]["x"] == {"a.v": 0}


# ── 4. 核验（只做强方向） ──

def test_solver_returning_undeclared_key_fails():
    spec = parse_spec(_spec([_item()], solvers={"solve": lambda *a: {"ghost": 1}}))
    with pytest.raises(ConfigError, match="未声明的容器键"):
        Elaborator(spec).run(
            _Source(file=[Atom(key="a.v", node=Node("Root"))]), {}
        )


def test_solver_must_return_mapping_or_none():
    spec = parse_spec(_spec([_item()], solvers={"solve": lambda *a: 5}))
    with pytest.raises(ConfigError, match="须返回表或 None"):
        Elaborator(spec).run(
            _Source(file=[Atom(key="a.v", node=Node("Root"))]), {}
        )


def test_no_atoms_is_not_an_error():
    """某 scope 下没有原子 → 项跑过但容器空，不报错（按原子出产物）。"""
    spec = parse_spec(_spec([_item(scope=SCOPE_UNIT)]))
    extra: dict = {}
    result = Elaborator(spec).run(_Source(), extra)
    assert extra[CTX_ELABORATION] == {"x": {}}
    assert result.ran == ("x",)


# ── 5. 降级（未声明能力） ──

def test_undeclared_capability_degrades_with_no_side_effect():
    source = _Source(file=[Atom(key="a.v", node=Node("Root"))])
    extra: dict = {}
    el = Elaborator(None)
    result = el.run(source, extra)

    assert el.declared is False
    assert CTX_ELABORATION not in extra  # 不注入容器
    assert result.products == {} and result.ran == ()
    assert source.calls == []  # 连原子都不枚举
    assert el.container() == {}


# ── 6. 读取点（能力查找） ──

def test_loader_returns_none_for_pack_without_capability():
    """未声明 `elaborator` 的语言包 → None（降级）。c4 不会声明，此断言长期稳定。"""
    from analyzer.checker import ProjectChecker

    ProjectChecker(rules_dir="grammar/c4")._prepare_run([])
    assert load_elaborator_spec("grammar/c4") is None


def test_loader_parses_capability_entry(monkeypatch):
    """入口返回值经 `parse_spec`（非法形态在此 fail-fast）。"""
    import core.plugin_loader as plugin_loader

    monkeypatch.setattr(
        plugin_loader,
        "get_capability_in",
        lambda name, rules_dir: (lambda: _spec([_item()])),
    )
    spec = load_elaborator_spec("grammar/whatever")
    assert spec is not None and spec.items[0].name == "x"


def test_loader_fails_fast_on_malformed_entry(monkeypatch):
    import core.plugin_loader as plugin_loader

    monkeypatch.setattr(
        plugin_loader,
        "get_capability_in",
        lambda name, rules_dir: (lambda: {"items": [_item(scope="nope")], "solvers": {}}),
    )
    with pytest.raises(ConfigError):
        load_elaborator_spec("grammar/whatever")
