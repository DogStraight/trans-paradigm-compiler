"""tests/core/test_rule_schema.py — GrammarRule 字段 schema 校验测试。

规则字段 schema 化（fail-fast）。
覆盖：
    - 未知顶层字段 → GrammarError
    - 未知 parser/renderer 阶段字段 → GrammarError
    - 布尔字段类型错 → GrammarError
    - analyzer 阶段宽松（插件原语开放，不误报）
    - 合法规则 / inject / transform 扩展点通过
    - load_all_toml 跳过 tpc.toml（配置段不污染规则集）
"""

import pytest

from core.errors import GrammarError
from core.define import GrammarRule, FileManager


class TestRuleSchema:
    """GrammarRule 字段 schema 校验。"""

    def test_unknown_top_level_field_rejected(self):
        with pytest.raises(GrammarError, match="未知顶层字段"):
            GrammarRule("Test", production=["a"], typo_field=1)

    def test_unknown_parser_field_rejected(self):
        with pytest.raises(GrammarError, match=r"\[parser\] 含未知字段"):
            GrammarRule("Test", parser={"production": ["a"], "typo": 1})

    def test_unknown_renderer_field_rejected(self):
        with pytest.raises(GrammarError, match=r"\[renderer\] 含未知字段"):
            GrammarRule("Test", renderer={"layout": {}, "typo": 1})

    def test_bool_field_type_rejected(self):
        with pytest.raises(GrammarError, match="is_statement 必须是布尔值"):
            GrammarRule("Test", is_statement="yes")

    def test_stage_bool_field_type_rejected(self):
        with pytest.raises(GrammarError, match=r"\[parser\].is_atom 必须是布尔值"):
            GrammarRule("Test", parser={"is_atom": "yes"})

    def test_analyzer_plugin_primitive_allowed(self):
        # analyzer 阶段宽松：scope/symbol 引擎字段 + 插件原语名开放
        rule = GrammarRule(
            "Test",
            analyzer={
                "scope": {"kind": "block"},
                "check_name_call": {"name_attr": "callee"},
            },
        )
        assert rule.analyzer["scope"]["kind"] == "block"

    def test_inject_transform_extensions_allowed(self):
        rule = GrammarRule(
            "Test",
            inject={"targets": ["Other"]},
            transform={"kind": "expand"},
        )
        assert rule.inject["targets"] == ["Other"]
        assert rule.transform["kind"] == "expand"

    def test_valid_rule_accepted(self):
        rule = GrammarRule(
            "Test",
            parser={"production": ["a", "b"], "is_atom": True},
            inline=True,
        )
        assert rule.production == ["a", "b"]
        assert rule.is_atom is True

    def test_peek_scope_allowed_in_parser(self):
        # _resolve_peek 会把 analyzer.scope 拷贝到 parser.scope
        rule = GrammarRule(
            "Test",
            parser={"production": ["a"], "scope": {"kind": "module"}},
        )
        assert rule.parser["scope"]["kind"] == "module"

    def test_node_binding_out_of_range_rejected(self):
        with pytest.raises(GrammarError, match="越界"):
            GrammarRule(
                "Test",
                parser={"production": ["a", "b"], "node": {"x": "$3"}},
            )

    def test_node_binding_in_range_ok(self):
        rule = GrammarRule(
            "Test",
            parser={"production": ["a", "b"], "node": {"x": "$2"}},
        )
        assert rule.node["x"] == "$2"

    def test_block_rule_binding_uses_stripped_production(self):
        # 块规则 production 剥离首尾字面 token 后剩 2 个 slot，$2 合法
        rule = GrammarRule(
            "Blk",
            is_block=True,
            parser={
                "production": ["kw.start", "a", "b", "kw.end"],
                "node": {"x": "$2"},
            },
        )
        assert rule.node["x"] == "$2"
        with pytest.raises(GrammarError, match="越界"):
            GrammarRule(
                "Blk2",
                is_block=True,
                parser={
                    "production": ["kw.start", "a", "b", "kw.end"],
                    "node": {"x": "$3"},
                },
            )

    def test_node_binding_path_variant_not_rejected(self):
        # $N.path 不校验子路径存在性（choice 分支形态差异是设计语义）
        rule = GrammarRule(
            "Test",
            parser={"production": ["@X|@Y"], "node": {"port_type": "$1.port_type"}},
        )
        assert rule.node["port_type"] == "$1.port_type"

    def test_node_binding_list_spec_validated(self):
        # list 规约中的每个 $N 都参与越界校验
        with pytest.raises(GrammarError, match="越界"):
            GrammarRule(
                "Test",
                parser={
                    "production": ["a", "b"],
                    "node": {"items": ["$1", "$3"]},
                },
            )


class TestLoadAllTomlSkipsTpc:
    """load_all_toml 跳过 tpc.toml（配置段不污染规则集）。"""

    def test_tpc_toml_not_loaded_as_rules(self, tmp_path):
        # 构造一个含 tpc.toml（配置段）与规则文件的目录
        (tmp_path / "tpc.toml").write_text(
            '[lexer]\ntoken_base = { file = "base/_token.toml" }\n', encoding="utf-8"
        )
        (tmp_path / "00_rules.toml").write_text(
            '[MyRule.parser]\nproduction = ["a"]\n', encoding="utf-8"
        )
        # tmp_path 在项目外，相对路径解析会失败——改为在 grammar/ 下建临时
        # 目录，直接验证 load_all_toml 对 tpc.toml 的跳过逻辑（[lexer] 配置
        # 段不进规则集）。
        import os
        import shutil
        from core.define import FileManager as FM

        proj_tmp = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            ),
            "grammar",
            "_tmp_schema_test",
        )
        os.makedirs(proj_tmp, exist_ok=True)
        try:
            shutil.copy(str(tmp_path / "tpc.toml"), os.path.join(proj_tmp, "tpc.toml"))
            shutil.copy(
                str(tmp_path / "00_rules.toml"),
                os.path.join(proj_tmp, "00_rules.toml"),
            )
            merged = FM.load_all_toml("grammar/_tmp_schema_test")
            # tpc.toml 的 [lexer] 段不应出现在规则集
            assert "lexer" not in merged
            assert "MyRule" in merged
        finally:
            shutil.rmtree(proj_tmp, ignore_errors=True)


class TestGetFullPathAbsolute:
    """get_full_path 对绝对路径必须原样返回（回归：POSIX 上曾因 lstrip('/')
    把绝对路径当相对路径重复拼接 _base_dir，导致 grammar 路径翻倍）。"""

    def test_absolute_path_returned_as_is(self):
        from core.define import FileManager as FM
        import os

        abs_path = os.path.join(FM._base_dir, "grammar", "verilog")
        result = FM.get_full_path(abs_path)
        assert os.path.isabs(result)
        assert os.path.normpath(result) == os.path.normpath(abs_path)
        # 翻倍回归探测：grammar 出现次数不得多于输入
        assert result.count("grammar") == abs_path.count("grammar")

    def test_relative_path_resolves_under_base_dir(self):
        from core.define import FileManager as FM
        import os

        result = FM.get_full_path("grammar/verilog")
        assert result == os.path.join(FM._base_dir, "grammar", "verilog")
