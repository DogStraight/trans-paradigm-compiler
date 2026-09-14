"""tests/engine/pipeline/test_contract_check.py — pass 契约校验（0.1.2 阶段 7）。

ADR-0015 §3：插件**注册时**声明 `produces` / `requires`（显式平铺名列表，
**时点不在插件侧**）；引擎在**时点边界**机械核验：

- 执行前：requires 已被前面的单元满足 → 未满足即 fail-fast；
- 执行后（切片 2）：声明的 produces 须**真产出**（生产方在 process 内经
  `note_produced` 登记；未产出不得声明）+ 可选**形状**（`shapes=`）核验。

无声明 = 不参与校验（可选能力）。
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
        del root_scope  # TransformPlugin.process 协议签名参数
        self.note_produced("thing", None)
        return ast


class _Consumer(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        return ast


class _NeedsScope(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        return ast


class _Plain(TransformPlugin):
    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        return ast


class _Liar(TransformPlugin):
    """声明 produces 但 process 不登记物化 → 执行后核验应拦下。"""

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        return ast


class _ShapeDict(TransformPlugin):
    """形状声明 dict + 物化 dict → 通过。"""

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        self.note_produced("obj", {"k": 1})
        return ast


class _ShapeBad(TransformPlugin):
    """形状声明 dict + 物化 list → 形状核验应拦下。"""

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        self.note_produced("obj", [1, 2])
        return ast


class _ShapeEmpty(TransformPlugin):
    """声明 non_empty + 物化空 dict → 核验应拦下。"""

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        self.note_produced("obj2", {})
        return ast


class _ExtraNoter(TransformPlugin):
    """物化未声明的产物 → 契约双向核验应拦下。"""

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        self.note_produced("thing", None)
        self.note_produced("bonus", None)
        return ast


_PROBE_NAMES = (
    "test.prod",
    "test.cons",
    "test.needs_scope",
    "test.plain",
    "test.liar",
    "test.shape_ok",
    "test.shape_bad",
    "test.shape_empty",
    "test.extra",
)


@pytest.fixture
def probes():
    """注册探针插件（带契约/形状），测后从全局注册面移除。"""
    from transform import engine

    order = len(engine._plugin_registry)
    engine.register_plugin(_Producer, name="test.prod", produces=["thing"])
    engine.register_plugin(_Consumer, name="test.cons", requires=["thing"])
    engine.register_plugin(_NeedsScope, name="test.needs_scope", requires=["scope"])
    engine.register_plugin(_Plain, name="test.plain")
    engine.register_plugin(_Liar, name="test.liar", produces=["ghost"])
    engine.register_plugin(
        _ShapeDict,
        name="test.shape_ok",
        produces=["obj"],
        shapes={"obj": {"type": "dict"}},
    )
    engine.register_plugin(
        _ShapeBad,
        name="test.shape_bad",
        produces=["obj"],
        shapes={"obj": {"type": "dict"}},
    )
    engine.register_plugin(
        _ShapeEmpty,
        name="test.shape_empty",
        produces=["obj2"],
        shapes={"obj2": {"non_empty": True}},
    )
    engine.register_plugin(_ExtraNoter, name="test.extra", produces=["thing"])
    try:
        yield
    finally:
        del engine._plugin_registry[order:]
        for qname in _PROBE_NAMES:
            engine._plugin_index.pop(qname, None)
            engine._plugin_contracts.pop(qname, None)
            engine._plugin_shapes.pop(qname, None)


def _run(schedules, ctx=None, **kw):  # noqa: ANN001, ANN002, ANN003
    from pipeline.schedule import _run_schedule

    ctx = ctx or _Ctx()
    return _run_schedule(ctx, Node("Root"), object(), "s", schedules, None, **kw), ctx


def test_missing_requirement_fails_fast(probes) -> None:
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    with pytest.raises(ValueError, match="requires 未满足: thing"):
        _run({"s": [PassDecl("c", "transform", impl="test.cons", plugin="test.cons")]})


def test_producer_before_consumer_satisfies(probes) -> None:
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    (ast, _), ctx = _run(
        {
            "s": [
                PassDecl("p", "transform", impl="test.prod", plugin="test.prod"),
                PassDecl("c", "transform", impl="test.cons", plugin="test.cons"),
            ]
        }
    )
    assert ast is not None
    assert any("pass: c" in m for m in ctx.logs)
    # trace 记录物化产物与依赖声明（来源核验：可用集 = 实际产出）
    assert ctx.result["trace"][0]["produced"] == ["thing"]
    assert "produced" not in ctx.result["trace"][1]
    assert ctx.result["trace"][1]["requires"] == ["thing"]
    assert "requires" not in ctx.result["trace"][0]  # 无声明不带（非空才带）


def test_analyze_disabled_leaves_scope_unavailable(probes) -> None:
    """analyze 被开关过滤 → 其 produces（scope）不并入可用集 → 依赖它的单元报错。"""
    del probes  # fixture 依赖声明（注册探针插件）
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
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    (ast, _), _ = _run(
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


def test_declared_produce_not_materialized_fails_fast(probes) -> None:
    """声明 produces 但未物化登记 → 执行后核验 fail-fast（声明不空转）。"""
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    with pytest.raises(ValueError, match="声明的产物未物化: ghost"):
        _run({"s": [PassDecl("l", "transform", impl="test.liar", plugin="test.liar")]})


def test_producer_note_extra_product_fails_fast(probes) -> None:
    """物化未声明的产物 → 契约双向核验 fail-fast（声明 = 物化）。"""
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    with pytest.raises(ValueError, match="未声明的产物: bonus"):
        _run({"s": [PassDecl("e", "transform", impl="test.extra", plugin="test.extra")]})


def test_shape_mismatch_fails_fast(probes) -> None:
    """形状声明 dict 但物化 list → 执行后形状核验 fail-fast。"""
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    with pytest.raises(ValueError, match="形状不符: 声明 dict"):
        _run(
            {
                "s": [
                    PassDecl(
                        "s", "transform", impl="test.shape_bad", plugin="test.shape_bad"
                    )
                ]
            }
        )


def test_shape_non_empty_fails_fast(probes) -> None:
    """声明 non_empty 但物化空 → 形状核验 fail-fast。"""
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    with pytest.raises(ValueError, match="non_empty，实为空"):
        _run(
            {
                "s": [
                    PassDecl(
                        "s",
                        "transform",
                        impl="test.shape_empty",
                        plugin="test.shape_empty",
                    )
                ]
            }
        )


def test_shape_declaration_passes(probes) -> None:
    """形状声明 dict + 物化 dict → 通过。"""
    del probes  # fixture 依赖声明（注册探针插件）
    from pipeline.schedule import PassDecl

    (ast, _), _ = _run(
        {"s": [PassDecl("s", "transform", impl="test.shape_ok", plugin="test.shape_ok")]}
    )
    assert ast is not None


def test_shape_spec_validated_at_register() -> None:
    """形状声明注册期 fail-fast：非法 token / 键不在 produces，且不改注册面。"""
    from transform import engine

    class _X(TransformPlugin):
        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            del root_scope  # 协议签名参数
            return ast

    before = len(engine._plugin_registry)
    with pytest.raises(ValueError, match="type 非法"):
        engine.register_plugin(
            _X, name="test.badspec", produces=["a"], shapes={"a": {"type": "tuple"}}
        )
    with pytest.raises(ValueError, match="不在 produces"):
        engine.register_plugin(
            _X, name="test.badkey", produces=["a"], shapes={"b": {"type": "dict"}}
        )
    with pytest.raises(ValueError, match="未知键"):
        engine.register_plugin(
            _X, name="test.badfield", produces=["a"], shapes={"a": {"kind": "dict"}}
        )
    assert len(engine._plugin_registry) == before  # 注册期校验失败不落注册面
    for qname in ("test.badspec", "test.badkey", "test.badfield"):
        assert qname not in engine._plugin_index


def test_real_plugins_declare_contracts() -> None:
    import importlib

    # 三个真实插件模块：导入即注册（副作用导入，名称本身不用）
    for _mod in (
        "transform._semantic_mapping",
        "transform.config_driven",
        "transform.slot_runner",
    ):
        importlib.import_module(_mod)
    from transform.engine import get_plugin_shapes

    contracts = get_plugin_contracts()
    assert contracts["SemanticMappingPlugin"]["produces"] == ["mapping_tables"]
    assert contracts["ConfigDrivenTransform"]["requires"] == ["mapping_tables"]
    assert contracts["slot_runner"]["requires"] == ["scope"]
    assert contracts["slot_runner"]["produces"] == ["slot_transforms"]
    # 形状声明（切片 2）：产物形状机械可核验
    assert get_plugin_shapes()["SemanticMappingPlugin"] == {
        "mapping_tables": {"type": "dict"}
    }


def test_plugin_registration_rejects_without_timepoint() -> None:
    """契约只含 produces/requires——插件侧不接受时点参数（时点归管线配置）。"""
    import inspect

    from transform import engine

    params = inspect.signature(engine.register_plugin).parameters
    assert "produces" in params and "requires" in params
    assert not {"order", "after", "point", "slot"} & set(params)
