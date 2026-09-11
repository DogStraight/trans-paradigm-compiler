"""tests/engine/transform/test_plugin_index.py — 插件身份面（0.1.2 5b-3a）。

ADR-0015 §1：单元粒度 = **插件实例化对象** → 插件须可寻址（管线配置
`[pipeline.units.<name>].impl` 按限定名引用）。本文件锁：
    - 引擎插件以类名为限定名注册（`SemanticMappingPlugin` 等）；
    - 语言插件用 `<组件名>.<单元名>`（`typed_ports.bridge`、`asm_gen.codegen`）；
    - 索引同名首胜（同源码多路径 import 是既有常态，不报错）；
    - `_plugin_registry`（执行序）语义不变。
"""

from transform.engine import TransformPlugin, get_plugin_index, plugin_name_of


def test_engine_plugins_registered_by_qualname() -> None:
    from transform import _semantic_mapping, config_driven  # noqa: F401

    idx = get_plugin_index()
    assert "SemanticMappingPlugin" in idx
    assert "ConfigDrivenTransform" in idx


def test_language_plugin_uses_component_qualified_name() -> None:
    """语言插件限定名 = `<组件名>.<单元名>`（verilog typed_ports 桥）。"""
    import grammar.verilog.plugins.typed_ports._bridge  # noqa: F401

    idx = get_plugin_index()
    assert "typed_ports.bridge" in idx
    assert plugin_name_of(idx["typed_ports.bridge"]) == "typed_ports.bridge"


def test_c4_plugin_uses_component_qualified_name() -> None:
    from grammar.c4.plugins.asm_gen import _asm  # noqa: F401

    idx = get_plugin_index()
    assert "asm_gen.codegen" in idx
    assert plugin_name_of(idx["asm_gen.codegen"]) == "asm_gen.codegen"


def test_duplicate_name_first_wins_and_registry_order_kept() -> None:
    """同名重复注册：索引首胜；registry 仍保留两者（执行序语义不变）。"""
    from transform import engine

    class DupA(TransformPlugin):
        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            return ast

    class DupB(TransformPlugin):
        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            return ast

    order = len(engine._plugin_registry)
    try:
        engine.register_plugin(DupA, name="dup.test")
        engine.register_plugin(DupB, name="dup.test")
        assert get_plugin_index()["dup.test"] is DupA
        assert engine._plugin_registry[order:] == [DupA, DupB]
    finally:
        del engine._plugin_registry[order:]
        engine._plugin_index.pop("dup.test", None)


def test_plugin_name_of_falls_back_to_class_name() -> None:
    class Unregistered(TransformPlugin):
        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            return ast

    assert plugin_name_of(Unregistered) == "Unregistered"
