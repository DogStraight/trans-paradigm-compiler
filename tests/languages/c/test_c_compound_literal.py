"""tests/languages/c/test_c_compound_literal.py — T2a：typedef 名复合字面量直接建树（#53）。

`(t){1}` / `(S){ .a = 1 }` 由 `CompoundLiteral` 的 `@CastTypeName|@CastTypedefName`
门控支直接解析；不经 raw 兜底（pre_scan 退役后也无 raw 来源）。

变异判据：去掉该分支 ⇒ 本文件红（`tools/check_gate_efficacy.py`）。
"""

import os

from core.config_registry import ConfigRegistry
from core.define import iter_nodes
from pipeline import run_pipeline_on_source

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")


def _run(src: str) -> dict:
    return run_pipeline_on_source(
        source=src,
        input_path="case.c",
        out_dir=None,
        quiet=True,
        rules_dir=_RULES,
        ext_dirs=[_PLUGINS],
    )


def _nodes(ast) -> list[str]:
    return [n.node_name for n in iter_nodes(ast)] if ast is not None else []


CASES = {
    "标量复合字面量": "typedef int t;\nx = (t){1};\n",
    "结构体复合字面量": (
        "typedef struct S { int a; } S;\nS s = (S){ .a = 1 };\n"
    ),
    "函数内复合字面量": "typedef int t;\nvoid f(void){ x = (t){1}; }\n",
}


class TestTypedefCompoundLiteral:
    """解析/结构/无 raw 三条判据。"""

    def test_parses_directly(self, config_loaded):
        del config_loaded
        ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
        try:
            for label, src in CASES.items():
                res = _run(src)
                assert res.get("success") is True and not res.get("error"), (
                    label,
                    res.get("error"),
                )
        finally:
            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )

    def test_structure_and_no_raw(self, config_loaded):
        del config_loaded
        ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
        try:
            for label, src in CASES.items():
                names = _nodes(_run(src)["ast"])
                assert "CompoundLiteral" in names, label
                assert "RawStatement" not in names, label
        finally:
            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )

    def test_plain_parenthesized_value_is_not_compound_literal(self, config_loaded):
        """反向：变量名不是 typedef ⇒ `(a){...}` 不建 CompoundLiteral（门控）。"""
        del config_loaded
        ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
        try:
            names = _nodes(_run("void f(void){ int a; x = (a){1}; }")["ast"])
            assert "CompoundLiteral" not in names
        finally:
            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )
