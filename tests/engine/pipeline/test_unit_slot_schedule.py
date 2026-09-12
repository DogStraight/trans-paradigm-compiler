"""槽位级单元（0.1.2 5b-3c-3）：槽位各自可声明时点。

`[pipeline.units.<name>] slot = "<槽位名>"`（与 `impl` 互斥）→ 该单元只跑该槽位
（引擎 `slot_runner` 单槽位执行），时点在管线配置里编排。槽位声明/注册查询在本
文件用 monkeypatch 替换 —— 不依赖组件加载链（原因见 engineering-gaps）。
"""

from core.define import Node
from transform.slot_runner import SlotRunnerPlugin

SCOPE = object()


class _Ctx:
    rules: dict = {}

    def log(self, _msg: str) -> None:
        return None


def _tree(*names: str) -> Node:
    root = Node("Root")
    root.add_attr("sub_node", [Node(n) for n in names])
    return root


def _install(monkeypatch, decls: dict, handlers: dict, seen: list | None = None):
    """替换槽位声明/注册/通道查询（不依赖组件加载链）。"""
    import core.plugin_loader as pl

    monkeypatch.setattr(pl, "get_transform_slot_decls", lambda: dict(decls))
    monkeypatch.setattr(pl, "get_transform_slots", lambda: dict(handlers))
    monkeypatch.setattr(pl, "get_transform_ctx_channels", lambda: {})
    return seen if seen is not None else []


def _decl(name: str, result: str = "none", walk: str = "top", on=("T",)) -> dict:
    return {
        "name": name,
        "on": list(on),
        "walk": walk,
        "ctx": {},
        "result": result,
    }


# ── 声明面：units.slot → PassDecl ──


def test_slot_unit_builds_passdecl(monkeypatch) -> None:
    from pipeline.schedule import build_unit_schedule

    _install(monkeypatch, {"probe_slot": _decl("probe_slot")}, {"probe_slot": lambda n, c: n})
    seq = build_unit_schedule({"s1": {"type": "transform", "slot": "probe_slot"}})
    assert seq is not None
    assert [(d.name, d.kind, d.slot, d.impl) for d in seq] == [
        ("s1", "transform", "probe_slot", "slot:probe_slot")
    ]


def test_unknown_slot_fails_fast(monkeypatch) -> None:
    from pipeline.schedule import build_unit_schedule

    _install(monkeypatch, {"probe_slot": _decl("probe_slot")}, {})
    import pytest

    with pytest.raises(ValueError, match="未声明的槽位"):
        build_unit_schedule({"s1": {"type": "transform", "slot": "nope"}})


def test_slot_unit_requires_transform_type(monkeypatch) -> None:
    from pipeline.schedule import build_unit_schedule

    _install(monkeypatch, {"probe_slot": _decl("probe_slot")}, {})
    import pytest

    with pytest.raises(ValueError, match="槽位单元限 transform"):
        build_unit_schedule({"s1": {"type": "analyze", "slot": "probe_slot"}})


def test_slot_and_impl_mutually_exclusive() -> None:
    from pipeline.units import build_unit_sequence

    import pytest

    with pytest.raises(ValueError, match="slot 与 impl 互斥"):
        build_unit_sequence(
            {"s1": {"type": "transform", "slot": "x", "impl": "y"}}
        )


def test_missing_impl_and_slot_fails() -> None:
    from pipeline.units import build_unit_sequence

    import pytest

    with pytest.raises(ValueError, match="缺 impl 或 slot"):
        build_unit_sequence({"s1": {"type": "transform"}})


def test_slot_unit_uses_slot_runner_contract(monkeypatch) -> None:
    from pipeline.schedule import _contract_of, build_unit_schedule
    from transform import slot_runner  # noqa: F401

    _install(monkeypatch, {"probe_slot": _decl("probe_slot")}, {})
    seq = build_unit_schedule({"s1": {"type": "transform", "slot": "probe_slot"}})
    assert seq is not None
    assert _contract_of(seq[0]) == {
        "produces": ["slot_transforms"],
        "requires": ["scope"],
    }


# ── 执行面：单槽位 / result 接回语义 ──


def test_only_slot_runs_single_slot(monkeypatch) -> None:
    seen: list = []
    _install(
        monkeypatch,
        {"a": _decl("a"), "b": _decl("b")},
        {"a": lambda n, c: seen.append("a") or n, "b": lambda n, c: seen.append("b") or n},
    )
    root = _tree("T")
    SlotRunnerPlugin(only_slot="a").process(root, SCOPE)
    assert seen == ["a"]


def test_full_runner_runs_all_declared_slots(monkeypatch) -> None:
    seen: list = []
    _install(
        monkeypatch,
        {"a": _decl("a"), "b": _decl("b")},
        {"a": lambda n, c: seen.append("a") or n, "b": lambda n, c: seen.append("b") or n},
    )
    SlotRunnerPlugin().process(_tree("T"), SCOPE)
    assert seen == ["a", "b"]


def test_unknown_only_slot_fails(monkeypatch) -> None:
    import pytest

    _install(monkeypatch, {"a": _decl("a")}, {"a": lambda n, c: n})
    with pytest.raises(ValueError, match="未知槽位"):
        SlotRunnerPlugin(only_slot="nope").process(_tree("T"), SCOPE)


def test_result_remove_drops_node(monkeypatch) -> None:
    _install(
        monkeypatch,
        {"drop": _decl("drop", result="remove")},
        {"drop": lambda n, c: None},
    )
    root = _tree("T", "Keep")
    SlotRunnerPlugin().process(root, SCOPE)
    assert [c.node_name for c in root.sub_node] == ["Keep"]


def test_result_extra_does_not_rewire_ast(monkeypatch) -> None:
    """extra：额外产物由 handler 自出（mark_extra），返回值**不接回** AST。

    回归（2026-09-12 e2e 抓到）：返回值若接回，`build_wrapper` 的 wrapper 模块
    会被内联进主输出（保真度 0.43）——桥原本丢弃返回值。
    """
    _install(
        monkeypatch,
        {"wrap": _decl("wrap", result="extra")},
        {"wrap": lambda n, c: Node("Wrapper")},
    )
    root = _tree("T")
    SlotRunnerPlugin().process(root, SCOPE)
    assert [c.node_name for c in root.sub_node] == ["T"]


def test_result_none_keeps_returned_node(monkeypatch) -> None:
    """none：原地变换——接回 handler 返回值。"""
    _install(
        monkeypatch,
        {"swap": _decl("swap", result="none")},
        {"swap": lambda n, c: Node("Rewired")},
    )
    root = _tree("T")
    SlotRunnerPlugin().process(root, SCOPE)
    assert [c.node_name for c in root.sub_node] == ["Rewired"]


def test_result_replace_migrates_comments(monkeypatch) -> None:
    def _fn(node, ctx):  # noqa: ANN001, ANN201
        return Node("New")

    _install(
        monkeypatch, {"swap": _decl("swap", result="replace")}, {"swap": _fn}
    )
    root = _tree("T")
    old = root.sub_node[0]
    old.add_attr("_comment_slots", {"trailing": ["// c"]})
    SlotRunnerPlugin().process(root, SCOPE)
    new = root.sub_node[0]
    assert new.node_name == "New"
    assert getattr(new, "_comment_slots", None) == {"trailing": ["// c"]}


def test_recursive_walk_visits_nested(monkeypatch) -> None:
    seen: list = []
    _install(
        monkeypatch,
        {"deep": _decl("deep", walk="recursive", on=("T",))},
        {"deep": lambda n, c: seen.append(n.node_name) or n},
    )
    root = Node("Root")
    inner = Node("Inner")
    inner.add_attr("sub_node", [Node("T")])
    root.add_attr("sub_node", [inner])
    SlotRunnerPlugin().process(root, SCOPE)
    assert seen == ["T"]


def test_run_pass_transform_slot_path(monkeypatch) -> None:
    seen: list = []
    _install(
        monkeypatch,
        {"probe_slot": _decl("probe_slot", on=("ProbeNode",))},
        {"probe_slot": lambda n, c: seen.append(n.node_name) or n},
    )
    from pipeline.schedule import PassState, _run_pass_transform

    root = _tree("ProbeNode")
    state = PassState(ast=root, scope=SCOPE, ctx=_Ctx())
    _run_pass_transform(state, {}, None, "probe_slot")
    assert seen == ["ProbeNode"]
    assert state.transformer is not None
    assert len(state.transformer.plugins) == 1
