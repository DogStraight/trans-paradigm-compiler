"""tests/engine/transform/test_plugin_index.py — 插件身份面（0.1.2 5b-3a）。

ADR-0015 §1：单元粒度 = **插件实例化对象** → 插件须可寻址（管线配置
`[pipeline.units.<name>].impl` 按限定名引用）。本文件锁：
    - 引擎插件以类名为限定名注册（`SemanticMappingPlugin` 等）；
    - 引擎插件可用语义限定名（`slot_runner` = 通用槽位执行器）；
    - 语言插件用 `<组件名>.<单元名>`（`asm_gen.codegen`）；
    - 索引同名首胜（同源码多路径 import 是既有常态，不报错）；
    - `_plugin_registry`（执行序）语义不变。
"""

from transform.engine import TransformPlugin, get_plugin_index, plugin_name_of


def test_engine_plugins_registered_by_qualname() -> None:
    import importlib

    # 两个插件模块：导入即注册（副作用导入，名称本身不用）
    importlib.import_module("transform._semantic_mapping")
    importlib.import_module("transform.config_driven")

    idx = get_plugin_index()
    assert "SemanticMappingPlugin" in idx
    assert "ConfigDrivenTransform" in idx


def test_engine_slot_runner_registered() -> None:
    """通用槽位执行器（引擎插件，语言无关）：语义限定名 `slot_runner`。"""
    import importlib

    # slot_runner 模块：导入即注册（副作用导入，名称本身不用）
    importlib.import_module("transform.slot_runner")

    idx = get_plugin_index()
    assert "slot_runner" in idx
    assert plugin_name_of(idx["slot_runner"]) == "slot_runner"


def test_c4_plugin_uses_component_qualified_name() -> None:
    # 注册是 import 期副作用（@register_plugin），而模块导入有缓存 → 前序测试
    # 导入过就不会重放；且插件注册表属"语言安装态"，模块结束即被还原。
    # 因此显式 reload 重放注册，不依赖跨模块的注册残留。
    import importlib

    from grammar.c4.plugins.asm_gen import _asm

    importlib.reload(_asm)

    idx = get_plugin_index()
    assert "asm_gen.codegen" in idx
    assert plugin_name_of(idx["asm_gen.codegen"]) == "asm_gen.codegen"


def test_duplicate_name_first_wins_and_registry_order_kept() -> None:
    """同名重复注册：索引首胜；registry 仍保留两者（执行序语义不变）。"""
    from transform import engine

    class DupA(TransformPlugin):
        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            del root_scope  # 协议签名参数
            return ast

    class DupB(TransformPlugin):
        def process(self, ast, root_scope):  # noqa: ANN001, ANN201
            del root_scope  # 协议签名参数
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
            del root_scope  # 协议签名参数
            return ast

    assert plugin_name_of(Unregistered) == "Unregistered"
