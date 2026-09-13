"""插件级加工单元（0.1.2 5b-3a）：同一变换按插件拆时点（声明面 + 单插件执行）。

ADR-0015 §1：`impl` 支持三种形态——`builtin.*`（内置执行器）/ `file.py:fn`
（处理器）/ **插件限定名**（插件级单元）。声明面先行：未声明 units 的语言包
仍走 `builtin.transform`（现行为，零变化）；显式声明后每插件一个单元/时点。
"""

import pytest

from core.define import Node
from transform.engine import TransformPlugin


class _Ctx:
    """`_run_pass_transform` 所需的最小 ctx 替身。"""

    rules: dict = {}

    def log(self, _msg: str) -> None:
        return None


class _Probe(TransformPlugin):
    seen: list[str] = []

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        _Probe.seen.append("probe")
        return ast


class _Other(TransformPlugin):
    seen: list[str] = []

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        _Other.seen.append("other")
        return ast


def test_plugin_units_build_plugin_bound_passdecls() -> None:
    from pipeline.schedule import build_unit_schedule

    seq = build_unit_schedule(
        {
            "map": {"type": "transform", "impl": "SemanticMappingPlugin"},
            "codegen": {
                "type": "transform",
                "impl": "ConfigDrivenTransform",
                "after": "map",
            },
        }
    )
    assert seq is not None
    assert [(d.name, d.kind, d.plugin) for d in seq] == [
        ("map", "transform", "SemanticMappingPlugin"),
        ("codegen", "transform", "ConfigDrivenTransform"),
    ]


def test_unknown_plugin_fails_fast() -> None:
    from pipeline.schedule import build_unit_schedule

    with pytest.raises(ValueError, match="未注册的变换插件"):
        build_unit_schedule({"t": {"type": "transform", "impl": "no.such.plugin"}})


def test_plugin_impl_requires_transform_type() -> None:
    from pipeline.schedule import build_unit_schedule

    with pytest.raises(ValueError, match="插件单元目前限 transform"):
        build_unit_schedule(
            {"a": {"type": "analyze", "impl": "SemanticMappingPlugin"}}
        )


def test_plugin_unit_params_matching_signature_accepted() -> None:
    """params 与插件构造器签名匹配 → 进 PassDecl（5b-3b）。"""
    from pipeline.schedule import build_unit_schedule

    seq = build_unit_schedule(
        {
            "t": {
                "type": "transform",
                "impl": "SemanticMappingPlugin",
                "params": {"raw_config": {"x": {}}},
            }
        }
    )
    assert seq is not None
    assert seq[0].params == {"raw_config": {"x": {}}}


def test_plugin_unit_params_signature_mismatch_fail_fast() -> None:
    """params 与构造器签名不匹配（未知参数）→ 加载期 fail-fast。"""
    from pipeline.schedule import build_unit_schedule

    with pytest.raises(ValueError, match="构造器不匹配"):
        build_unit_schedule(
            {
                "t": {
                    "type": "transform",
                    "impl": "SemanticMappingPlugin",
                    "params": {"mode": "x"},
                }
            }
        )


def test_builtin_transform_rejects_unknown_builtin_impl() -> None:
    from pipeline.units import build_unit_sequence

    with pytest.raises(ValueError, match="非内置执行器"):
        build_unit_sequence({"t": {"type": "transform", "impl": "builtin.nope"}})


def test_run_pass_transform_runs_only_named_plugin() -> None:
    """插件单元执行：只跑该插件（不跑同注册表中其它插件）。"""
    from pipeline.schedule import PassState, _run_pass_transform
    from transform import engine

    order = len(engine._plugin_registry)
    try:
        engine.register_plugin(_Probe, name="test.probe")
        engine.register_plugin(_Other, name="test.other")
        _Probe.seen.clear()
        _Other.seen.clear()
        state = PassState(ast=Node("Root"), scope=object(), ctx=_Ctx())
        _run_pass_transform(state, {}, "test.probe")
        assert _Probe.seen == ["probe"]
        assert _Other.seen == [], "非目标插件被误跑"
        assert state.transformer is not None
        assert len(state.transformer.plugins) == 1
    finally:
        del engine._plugin_registry[order:]
        engine._plugin_index.pop("test.probe", None)
        engine._plugin_index.pop("test.other", None)


def test_unknown_plugin_at_execution_fails_fast() -> None:
    from pipeline.schedule import PassState, _run_pass_transform

    state = PassState(ast=Node("Root"), scope=object(), ctx=_Ctx())
    with pytest.raises(ValueError, match="未知变换插件"):
        _run_pass_transform(state, {}, "nope.nope")
