"""P2b-1：符号相关性标记（`symbol_dependent`）——**只标记，不摘诊断**。

口径（实现处 docstring 为准）：`symbol_dependent=True` ⟺ 未收敛位点的句子区间含
`( <pre_scan 名> )` 形态（`linter/lookahead.py::_symbol_hits`）。符号输入走引擎
`[lexer] pre_scan`（语言包声明驱动，引擎不硬编码任何 kind 名）。

**诊断摘除（P2b-2）与 parser 位点 raw（P3）同批落地**：本批用户可见面零变化——
门禁①的位点仍是 2 条 blocking 诊断（摘除与 raw 一起在 P3 引入）。

语言作用域是全局态：C 用例用完切回 verilog（同 `tests/languages/c/conftest.py` 纪律）。
"""

import pytest

from core.define import DEFAULT_EXT_DIRS, DEFAULT_RULES_DIR

C_PACK = "grammar/c"
C_PLUGINS = "grammar/c/plugins"


@pytest.fixture(scope="module")
def scanner(config_loaded):
    """verilog（默认包）LinterScanner——对照用。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    from linter.scanner import LinterScanner

    return LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)


@pytest.fixture
def c_scanner(config_loaded):
    """C 包 LinterScanner（用完切回 verilog）。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    from core.config_registry import ConfigRegistry
    from linter.scanner import LinterScanner

    ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
    try:
        yield LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


def _warns(scanner, src):
    diags = scanner.scan(src)
    return diags, scanner.internal_warnings()


class TestSymbolDependentMarking:
    """P2b-1 标记口径（正/负样本；用户诊断面另有用例锁）。"""

    def test_typedef_name_in_parens_marked(self, c_scanner):
        """① 门禁①：`typedef int myint;` + `x = (myint)y;` ⇒ 标记命中。"""
        _diags, warns = _warns(c_scanner, "typedef int myint;\nx = (myint)y;\n")
        assert len(warns) == 1
        w = warns[0]
        assert w["reason"] == "no_full_match"
        assert w["symbol_dependent"] is True
        assert w["symbol_names"] == ["myint"]
        assert w["symbol_shape"] == "paren_name"
        assert w["region"][0] < w["region"][1]

    def test_true_syntax_error_not_marked(self, c_scanner):
        """门禁②：`x = (1 + )y;` 无 pre_scan 名 ⇒ 不标记。"""
        diags, warns = _warns(c_scanner, "x = (1 + )y;\n")
        assert warns[0]["symbol_dependent"] is False
        assert warns[0]["symbol_names"] == []
        assert all(d.blocking for d in diags)

    def test_same_name_variable_not_marked(self, c_scanner):
        """门禁③（负向）：`int myint;` 里 `myint` 是变量 ⇒ 不得标符号相关。"""
        diags, warns = _warns(c_scanner, "int myint;\nmyint *b;\n")
        assert warns[0]["reason"] == "ambiguous_full_match"
        assert warns[0]["symbol_dependent"] is False
        assert diags == []  # 既有行为：原本就不报

    def test_undeclared_type_name_not_marked(self, c_scanner):
        """负向：`x = (myint)y;` 但无 typedef 声明 ⇒ 名不在 pre_scan ⇒ 不标记。"""
        _diags, warns = _warns(c_scanner, "x = (myint)y;\n")
        assert warns[0]["symbol_dependent"] is False

    def test_unrelated_name_in_parens_not_marked(self, c_scanner):
        """负向（隔离"名 ∈ pre_scan"那一半）：pre_scan 非空，括号内名不是已知名。

        上一条靠"pre_scan 为空"早退；本条 pre_scan 非空 ⇒ 只有"名判定"能挡住
        （缺陷态验证即打这一条）。
        """
        _diags, warns = _warns(c_scanner, "typedef int myint;\nz = (other)y;\n")
        assert warns[0]["symbol_dependent"] is False

    def test_typedef_pointer_not_marked(self, c_scanner):
        """`typedef int myint;` + `myint *b;`：位点含名但非括号形态 ⇒ 不标记。"""
        _diags, warns = _warns(c_scanner, "typedef int myint;\nmyint *b;\n")
        assert warns[0]["symbol_dependent"] is False

    def test_verilog_side_untouched(self, scanner):
        """verilog 对照：无 pre_scan 类型名 ⇒ 无标记、诊断照旧。"""
        diags = scanner.scan("module m; always @(*) begin a = 1; end endmodule\n")
        assert diags == []
        assert all(w["symbol_dependent"] is False for w in scanner.internal_warnings())


class TestMarkingIsNotSuppression:
    """本批**不摘诊断**（P2b-2 与 P3 同批）——锁定"零用户可见变化"。"""

    def test_gate1_diagnostics_unchanged(self, c_scanner):
        """门禁①位点仍是 2 条 blocking（`phase-unrecognized` + `phase-statement`）。"""
        diags, _warns_ = _warns(c_scanner, "typedef int myint;\nx = (myint)y;\n")
        assert [d.code for d in diags] == ["phase-unrecognized", "phase-statement"]
        assert all(d.blocking for d in diags)

    def test_gate2_diagnostics_unchanged(self, c_scanner):
        """门禁②位点仍是 3 条 blocking（真语法错不因符号面变化）。"""
        diags, _warns_ = _warns(c_scanner, "x = (1 + )y;\n")
        assert [d.code for d in diags] == [
            "phase-unrecognized",
            "phase-statement",
            "phase-statement",
        ]

    def test_record_has_no_downgrade_fields(self, c_scanner):
        """条目**不含**降级字段（P2b-2 推迟 ⇒ 不留死字段/死配置）。"""
        _diags, warns = _warns(c_scanner, "typedef int myint;\nx = (myint)y;\n")
        assert "downgraded" not in warns[0]
        assert "suppressed" not in warns[0]
        import linter.scanner as scanner_mod

        assert not hasattr(scanner_mod, "_DOWNGRADABLE_CODES")
        assert not hasattr(scanner_mod.LinterScanner, "_apply_narrow_downgrade")
