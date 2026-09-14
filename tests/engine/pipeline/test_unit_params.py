"""插件单元实例化参数（0.1.2 阶段 5b-3b）：`params` → 构造器关键字参数覆写。

机制：`[[pipeline.units.*]]` 的 `params` 表就是插件**构造器关键字参数**
（执行层 `cls(**params)`）；加载期按 `inspect.signature` 核验——未知参数 /
缺必需参数 → fail-fast（不静默忽略）。同一插件可多实例（各自参数与时点）；
槽位 / 内置 / handler 单元无实例化参数，声明 `params` 即 fail-fast。
"""

import pytest

from core.define import Node
from transform.engine import TransformPlugin


class _Ctx:
    """`_run_pass_transform` 所需的最小 ctx 替身。"""

    rules: dict = {}

    def log(self, _msg: str) -> None:
        del _msg  # log 协议签名参数（本桩不打日志）
        return None


class _ParamProbe(TransformPlugin):
    """记录每次实例化的构造参数（区分多实例）。"""

    inits: list[dict] = []

    def __init__(self, tag: str = "", mode: str | None = None) -> None:
        _ParamProbe.inits.append({"tag": tag, "mode": mode})

    def process(self, ast, root_scope):  # noqa: ANN001, ANN201
        del root_scope  # 协议签名参数
        return ast


def _register(engine, order: int) -> None:  # noqa: ANN001
    del order  # 调用点签名保持一致（本 helper 不读 order）
    engine.register_plugin(_ParamProbe, name="test.params")


def _cleanup(engine, order: int) -> None:  # noqa: ANN001
    del engine._plugin_registry[order:]
    engine._plugin_index.pop("test.params", None)


def test_plugin_params_build_and_execute() -> None:
    """params 进 PassDecl，执行期按构造器关键字参数实例化。"""
    from pipeline.schedule import PassState, _run_pass_transform, build_unit_schedule
    from transform import engine

    order = len(engine._plugin_registry)
    try:
        _register(engine, order)
        seq = build_unit_schedule(
            {"p": {"type": "transform", "impl": "test.params", "params": {"tag": "A"}}}
        )
        assert seq is not None
        assert seq[0].params == {"tag": "A"}
        _ParamProbe.inits.clear()
        state = PassState(ast=Node("Root"), scope=object(), ctx=_Ctx())
        _run_pass_transform(state, {}, "test.params", params={"tag": "A"})
        assert _ParamProbe.inits == [{"tag": "A", "mode": None}]
    finally:
        _cleanup(engine, order)


def test_same_plugin_two_instances_with_different_params() -> None:
    """同一插件多实例：各自 params（声明面）——多时点/多实例是设计用法。"""
    from pipeline.schedule import build_unit_schedule
    from transform import engine

    order = len(engine._plugin_registry)
    try:
        _register(engine, order)
        seq = build_unit_schedule(
            {
                "a": {
                    "type": "transform",
                    "impl": "test.params",
                    "params": {"tag": "A"},
                },
                "b": {
                    "type": "transform",
                    "impl": "test.params",
                    "params": {"tag": "B"},
                    "after": "a",
                },
            }
        )
        assert seq is not None
        assert [d.params["tag"] for d in seq] == ["A", "B"]
    finally:
        _cleanup(engine, order)


def test_unknown_param_fails_fast_at_build() -> None:
    """未知参数名（构造器签名外）→ 加载期 fail-fast。"""
    from pipeline.schedule import build_unit_schedule
    from transform import engine

    order = len(engine._plugin_registry)
    try:
        _register(engine, order)
        with pytest.raises(ValueError, match="构造器不匹配"):
            build_unit_schedule(
                {
                    "p": {
                        "type": "transform",
                        "impl": "test.params",
                        "params": {"nope": 1},
                    }
                }
            )
    finally:
        _cleanup(engine, order)


def test_params_on_slot_unit_fails_fast() -> None:
    from pipeline.schedule import build_unit_schedule

    with pytest.raises(ValueError, match="槽位单元不支持 params"):
        build_unit_schedule(
            {"s": {"type": "transform", "slot": "whatever", "params": {"x": 1}}}
        )


def test_params_on_builtin_fails_fast() -> None:
    from pipeline.schedule import build_unit_schedule

    with pytest.raises(ValueError, match="内置/处理器单元不支持 params"):
        build_unit_schedule(
            {
                "t": {
                    "type": "transform",
                    "impl": "builtin.transform",
                    "params": {"x": 1},
                }
            }
        )


def test_params_non_table_fails_fast_at_parse() -> None:
    from pipeline.units import build_unit_sequence

    with pytest.raises(ValueError, match="params 须为表"):
        build_unit_sequence({"t": {"type": "transform", "impl": "x", "params": [1]}})


def test_trace_entry_includes_params() -> None:
    """trace 条目带 params（非空才带，可视化）。"""
    from pipeline.schedule import PassDecl, PassState, _trace_entry

    state = PassState(ast=None, scope=None, ctx=_Ctx())
    decl = PassDecl(name="u", kind="check", impl="x.py:fn", params={"a": 1})
    entry = _trace_entry(0, decl, state, set())
    assert entry["params"] == {"a": 1}
