"""tests/engine/pipeline/test_contract_check.py — pass 契约校验（0.1.2 阶段 7）。

ADR-0015 §3：插件**注册时**声明 `produces` / `requires`（显式平铺名列表，
**时点不在插件侧**）；引擎在**时点边界**（单元执行前）机械核验 requires 是否
已被前面的单元满足 → 未满足即 fail-fast。无声明 = 不参与校验（可选能力）。
"""

import pytest

from core.define import Node
from transform.engine import TransformPlugin, get_plugin_contracts


class _Ctx:
    """`_run_schedule` 所需的最小 ctx 替身。"""

    def __init__(self) -> None:
        self.rules: dict = {}
        self.expand_enhanced = True
        self.analyzer_enabled = True
        self.transform_enabled = True
        self.stage: str | None = None
        self.result: dict = {}
        self.logs: list[str] = []

    def log(self, msg: str) -> None:
        self.logs.append(msg)


class _Producer(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        return ast


class _Consumer(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        return ast


class _NeedsScope(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        return ast


class _Plain(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        return ast


@pytest.fixture
def probes():
    """注册探针插件（带契约），测后从全局注册面移除。"""
    from transform import engine

    order = len(engine._plugin_registry)
    engine.register_plugin(_Producer, name="test.prod", produces=["thing"])
    engine.register_plugin(_Consumer, name="test.cons", requires=["thing"])
    engine.register_plugin(_NeedsScope, name="test.needs_scope", requires=["scope"])
    engine.register_plugin(_Plain, name="test.plain")
    try:
        yield
    finally:
        del engine._plugin_registry[order:]
        for qname in ("test.prod", "test.cons", "test.needs_scope", "test.plain"):
            engine._plugin_index.pop(qname, None)
            engine._plugin_contracts.pop(qname, None)


def _run(schedules, ctx=None, **kw):  # noqa: ANN001, ANN002, ANN003
    from pipeline.schedule import _run_schedule

    ctx = ctx or _Ctx()
    return _run_schedule(ctx, Node("Root"), object(), "s", schedules, None, **kw), ctx


def test_missing_requirement_fails_fast(probes) -> None:
    from pipeline.schedule import PassDecl

    with pytest.raises(ValueError, match="requires 未满足: thing"):
        _run({"s": [PassDecl("c", "transform", impl="test.cons", plugin="test.cons")]})


def test_producer_before_consumer_satisfies(probes) -> None:
    from pipeline.schedule import PassDecl

    (ast, _scope), ctx = _run(
        {
            "s": [
                PassDecl("p", "transform", impl="test.prod", plugin="test.prod"),
                PassDecl("c", "transform", impl="test.cons", plugin="test.cons"),
            ]
        }
    )
    assert ast is not None
    assert any("pass: c" in m for m in ctx.logs)


def test_analyze_disabled_leaves_scope_unavailable(probes) -> None:
    """analyze 被开关过滤 → 其 produces（scope）不并入可用集 → 依赖它的单元报错。"""
    from pipeline.schedule import PassDecl

    ctx = _Ctx()
    ctx.analyzer_enabled = False
    with pytest.raises(ValueError, match="requires 未满足: scope"):
        _run(
            {
                "s": [
                    PassDecl("analyze", "analyze", impl="builtin.analyze"),
                    PassDecl(
                        "bridge",
                        "transform",
                        impl="test.needs_scope",
                        plugin="test.needs_scope",
                    ),
                ]
            },
            ctx=ctx,
        )


def test_undeclared_contract_skips_check(probes) -> None:
    """无 produces/requires 声明 → 不参与校验（可选能力，零影响）。"""
    from pipeline.schedule import PassDecl

    (ast, _scope), _ctx = _run(
        {"s": [PassDecl("p", "transform", impl="test.plain", plugin="test.plain")]}
    )
    assert ast is not None


def test_builtin_transform_has_no_contract() -> None:
    """粗粒度内置执行器不声明契约（黑盒跑全部插件）→ 不校验。"""
    from pipeline.schedule import _contract_of, PassDecl

    assert _contract_of(PassDecl("t", "transform", impl="builtin.transform")) is None
    assert _contract_of(PassDecl("a", "analyze", impl="builtin.analyze")) == {
        "produces": ["scope"],
        "requires": [],
    }


def test_real_plugins_declare_contracts() -> None:
    from transform import _semantic_mapping, config_driven, slot_runner  # noqa: F401

    contracts = get_plugin_contracts()
    assert contracts["SemanticMappingPlugin"]["produces"] == ["mapping_tables"]
    assert contracts["ConfigDrivenTransform"]["requires"] == ["mapping_tables"]
    assert contracts["slot_runner"]["requires"] == ["scope"]
    assert contracts["slot_runner"]["produces"] == ["slot_transforms"]


def test_plugin_registration_rejects_without_timepoint() -> None:
    """契约只含 produces/requires——插件侧不接受时点参数（时点归管线配置）。"""
    import inspect

    from transform import engine

    params = inspect.signature(engine.register_plugin).parameters
    assert "produces" in params and "requires" in params
    assert not {"order", "after", "point", "slot"} & set(params)
