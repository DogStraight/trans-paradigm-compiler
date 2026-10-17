"""宏定义的**形式化语法**检查（linter 阶段，AST 前）。

作者定调（2026-10-17）：形式化语法错误走 linter（AST 前），语义级走 check 插件族。
本文件判据 = 每类非法形态给**带位置**的 blocking 诊断；合法形态零误报；
**语言包声明 `[macro_syntax]` 段才启用**（verilog 未声明 ⇒ 不跑，A/B 零变化）。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from linter import macro_syntax as macro_syntax_mod
from linter.macro_syntax import macro_syntax_diagnostics
from preprocessor.macro_shape import MacroSyntax, load_macro_syntax


@pytest.fixture
def c_lang(config_loaded):
    """切到 C 语言包（`_macro.toml` 声明了 `[macro_syntax]`），用完切回默认包。"""
    del config_loaded
    from core.config_registry import ConfigRegistry

    ConfigRegistry.load_language("grammar/c", plugins_dir="grammar/c/plugins")
    try:
        yield
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


@pytest.mark.parametrize(
    "src,code",
    [
        ("#define\n", "macro-name"),
        ("#define F(a,) a\n", "macro-param"),
        ("#define F(,a) a\n", "macro-param"),
        ("#define F(a b) a\n", "macro-param"),
        ("#define F(a,a) a\n", "macro-param"),
        ("#define F(...,a) a\n", "macro-param"),
        ("#define F(...) # ...\n", "macro-body"),
        ("#define S(x) # y\n", "macro-body"),
        ("#define P(x) ## x\n", "macro-body"),
        ("#define Q(x) x ##\n", "macro-body"),
    ],
)
def test_illegal_forms_reported_with_position(c_lang, src, code):
    """非法形态 ⇒ 对应码的 blocking 诊断，位置锚在定义所在行。"""
    diags = macro_syntax_diagnostics(src, "grammar/c")
    assert diags, f"应报诊断：{src!r}"
    assert diags[0].code == code, (src, [d.code for d in diags])
    assert diags[0].blocking
    assert diags[0].message
    assert diags[0].range[0].line == 0


@pytest.mark.parametrize(
    "src",
    [
        "#define X 1\n",
        "#define F(a, b) a + b\n",
        "#define V(...) __VA_ARGS__\n",
        "#define S(x) #x\n",
        "#define P(x, y) x ## y\n",
        "#define E() 1\n",
        "#define F(a) a\n",
    ],
)
def test_legal_forms_no_false_positive(c_lang, src):
    """合法形态零误报。"""
    assert macro_syntax_diagnostics(src, "grammar/c") == []


def test_declaration_face_is_source_of_the_check(config_loaded):
    """机制判据：C 声明了 `[macro_syntax]`（含变参占位），verilog 未声明 ⇒ 不启用。"""
    del config_loaded
    c_decl = load_macro_syntax(rules_dir="grammar/c")
    assert c_decl is not None and c_decl.variadic_marker == "..."
    assert load_macro_syntax(rules_dir=DEFAULT_RULES_DIR) is None


def test_verilog_not_check(config_loaded):
    """verilog 未声明 `[macro_syntax]` ⇒ 不跑（不把 C 的宏定义语法套到别的语言）。"""
    del config_loaded
    assert macro_syntax_diagnostics("`define F(a,) a\n", DEFAULT_RULES_DIR) == []


def test_variadic_marker_declaration_drives_check(c_lang, monkeypatch):
    """同一份源码：声明了变参占位 ⇒ 合法；未声明 ⇒ `...` 是非法形参项。"""
    src = "#define V(...) __VA_ARGS__\n"
    assert macro_syntax_diagnostics(src, "grammar/c") == []
    monkeypatch.setattr(
        macro_syntax_mod, "load_macro_syntax", lambda **_kw: MacroSyntax()
    )
    diags = macro_syntax_diagnostics(src, "grammar/c")
    assert [d.code for d in diags] == ["macro-param"]


def test_scanner_wires_blocking_diagnostic(c_lang):
    """linter 阶段（`LinterScanner.scan`）确实产出该诊断（用户可见、blocking）。"""
    from linter.scanner import LinterScanner

    scanner = LinterScanner(rules_dir="grammar/c", ext_dirs=["grammar/c/plugins"])
    diags = scanner.scan("#define F(a,) a\nint x;\n")
    hits = [d for d in diags if d.code == "macro-param" and d.blocking]
    assert hits, [d.code for d in diags]
