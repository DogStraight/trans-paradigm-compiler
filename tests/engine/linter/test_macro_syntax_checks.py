"""宏定义的**形式化语法**检查（linter 阶段，AST 前）。

作者定调（2026-10-17）：形式化语法错误走 linter（AST 前），语义级走 check 插件族。
本文件判据 = 每类非法形态给**带位置**的 blocking 诊断；合法形态零误报；
语言包未声明 `check_syntax` ⇒ 不跑（verilog 不受影响）。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from linter.macro_syntax import macro_syntax_diagnostics


@pytest.fixture
def c_lang(config_loaded):
    """切到 C 语言包（define 声明了 check_syntax），用完切回默认包。"""
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


def test_verilog_not_check(config_loaded):
    """verilog 未声明 check_syntax ⇒ 不跑（不把 C 的宏语法约束套到别的语言）。"""
    del config_loaded
    assert macro_syntax_diagnostics("`define F(a,) a\n", DEFAULT_RULES_DIR) == []


def test_scanner_wires_blocking_diagnostic(c_lang):
    """linter 阶段（`LinterScanner.scan`）确实产出该诊断（用户可见、blocking）。"""
    from linter.scanner import LinterScanner

    scanner = LinterScanner(rules_dir="grammar/c", ext_dirs=["grammar/c/plugins"])
    diags = scanner.scan("#define F(a,) a\nint x;\n")
    hits = [d for d in diags if d.code == "macro-param" and d.blocking]
    assert hits, [d.code for d in diags]
