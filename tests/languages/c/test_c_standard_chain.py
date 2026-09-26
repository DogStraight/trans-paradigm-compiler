"""tests/languages/c/test_c_standard_chain.py — C 标准包含关系（`requires` 链）。

ROADMAP 定调："C 标准演进 = 语法增量 + 关键字增量 + 预处理指令增量"，标准包含关系用
`requires` 链表达（c23 ⊇ c17 ⊇ c11 ⊇ 核心基线）。本文件验证**这条关系可执行**：

1. 真实包：`c11` + `c17` 都在启用清单里时可正常加载（c17 依赖 c11）；
2. **缺前置即响亮失败**：只给 c17 不给 c11 → 加载期报错（不是静默少加载）；
3. **环即失败**：互相依赖 → 报错（拓扑排序的既有行为，一并锁住）；
4. 插件清单数据面：`plugins/c17/tpc.toml` 确实声明了 `requires = ["c11"]`，
   且**不带语法文件**（C17 是缺陷修正版，忠于事实）。
"""

import os
import tomllib

import pytest

from core.plugin_loader import _resolve_dependencies

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_PACK = os.path.join(ROOT, "grammar", "c")


def _meta(name: str, requires: list[str] | None = None) -> dict:
    m: dict = {"name": name}
    if requires:
        m["requires"] = requires
    return m


class TestStandardChainIsExecutable:
    def test_missing_prerequisite_fails_loudly(self):
        """只给 c17 不给 c11 → 加载期失败（包含关系被强制）。"""
        with pytest.raises(ValueError, match="requires 'c11'"):
            _resolve_dependencies([_meta("c17", ["c11"])])

    def test_error_message_names_the_requirer(self):
        """报文要点名**依赖方**（修过的自指文案：不应出现 "c11 requires c11"）。"""
        with pytest.raises(ValueError) as exc:
            _resolve_dependencies([_meta("c17", ["c11"])])
        assert "'c17' requires 'c11'" in str(exc.value), str(exc.value)

    def test_chain_orders_prerequisite_first(self):
        metas = [_meta("c17", ["c11"]), _meta("c11", [])]
        ordered = [m["name"] for m in _resolve_dependencies(metas)]
        assert ordered.index("c11") < ordered.index("c17")

    def test_three_level_chain(self):
        """c23 ⊇ c17 ⊇ c11：三级链可拓扑排序且前置在先。"""
        metas = [_meta("c23", ["c17"]), _meta("c17", ["c11"]), _meta("c11", [])]
        ordered = [m["name"] for m in _resolve_dependencies(metas)]
        assert ordered == ["c11", "c17", "c23"]

    def test_cycle_is_rejected(self):
        with pytest.raises(ValueError, match="cycle"):
            _resolve_dependencies([_meta("c11", ["c17"]), _meta("c17", ["c11"])])


class TestPluginManifests:
    def test_c17_requires_c11(self):
        with open(os.path.join(_PACK, "plugins", "c17", "tpc.toml"), "rb") as f:
            meta = tomllib.load(f)
        assert meta.get("requires") == ["c11"]

    def test_c17_has_no_grammar_files(self):
        """C17 无新语法 —— 插件不带语法文件是**忠于事实**，不是漏做。"""
        with open(os.path.join(_PACK, "plugins", "c17", "tpc.toml"), "rb") as f:
            meta = tomllib.load(f)
        assert "grammar" not in meta

    def test_pack_enables_all_three_increments(self):
        with open(os.path.join(_PACK, "tpc.toml"), "rb") as f:
            meta = tomllib.load(f)
        enabled = meta["plugins"]["enabled"]
        assert {"c11", "c17", "c23"} <= set(enabled)

    def test_c23_requires_c17(self):
        with open(os.path.join(_PACK, "plugins", "c23", "tpc.toml"), "rb") as f:
            meta = tomllib.load(f)
        assert meta.get("requires") == ["c17"]

    def test_c23_carries_grammar_files(self):
        """c23 与 c17 不同：它有**真实语法增量**（小写 `static_assert` 关键字化）。"""
        with open(os.path.join(_PACK, "plugins", "c23", "tpc.toml"), "rb") as f:
            meta = tomllib.load(f)
        assert meta.get("grammar", {}).get("files"), "c23 应有语法文件"


class TestPackLoadsWithChain:
    def test_real_pack_loads(self, config_loaded):
        """真实包（c11 + c17 启用）可正常加载且 c11 的关键字生效。"""
        del config_loaded
        from core.config_registry import ConfigRegistry
        from lexer import Lexer

        ConfigRegistry.load_language(_PACK, plugins_dir=os.path.join(_PACK, "plugins"))
        try:
            lexer = Lexer(rules_dir=_PACK)
            types = [t.type for t in lexer.tokenize("_Static_assert\n") if t.type != "newline"]
            assert types == ["keyword._Static_assert"]
        finally:
            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )


class TestC23IncrementWorks:
    def test_static_assert_parses_with_c23(self, config_loaded):
        """小写 `static_assert(1, "x");` → `StaticAssertC23Decl`（C23 关键字化生效）。"""
        del config_loaded
        import os as _os

        from core.config_registry import ConfigRegistry
        from core.define import GrammarRulesRegister
        from lexer import Lexer
        from parser import setup_grammar
        from parser.parser_core import Parser
        from parser.rule_selector import RuleSelector

        ConfigRegistry.load_language(_PACK, plugins_dir=_os.path.join(_PACK, "plugins"))
        try:
            register = GrammarRulesRegister()
            rules = setup_grammar(_PACK, register)
            stmt = [
                n
                for n, r in rules.items()
                if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
            ]
            parser = Parser(
                rules_dir=_PACK,
                rules=rules,
                rule_selector=RuleSelector(rules, stmt),
                log_file="",
            )
            ast = parser.parse(
                Lexer(rules_dir=_PACK).tokenize('static_assert(1, "x");\n')
            )
            assert ast is not None
            assert [n.node_name for n in ast.sub_node] == ["StaticAssertC23Decl"]
        finally:
            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )

    def test_c23_keywords_are_lexed(self, config_loaded):
        """C23 关键字词法面生效（`typeof`/`constexpr` 等即使暂无规则也是关键字）。"""
        del config_loaded
        import os as _os

        from core.config_registry import ConfigRegistry
        from lexer import Lexer

        ConfigRegistry.load_language(_PACK, plugins_dir=_os.path.join(_PACK, "plugins"))
        try:
            lexer = Lexer(rules_dir=_PACK)
            for word in ("typeof", "constexpr", "nullptr", "bool", "true"):
                types = [x.type for x in lexer.tokenize(word + "\n") if x.type != "newline"]
                assert types == [f"keyword.{word}"], f"{word} -> {types}"
        finally:
            ConfigRegistry.load_language(
                "grammar/verilog", plugins_dir="grammar/verilog/plugins"
            )
