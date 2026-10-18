"""预处理问题诊断的两路径共用入口（A2 两路径统一）：`preprocessor.scan_diagnostics`。

判据：同一输入 `tpc lint`（直连 scanner）与 `tpc check`（ProjectChecker）都要能拿到
**同类**预处理诊断、且不抛异常。CLI 侧只做"打印 + 退出码"，判定逻辑在这里单测。
"""
import pytest

from core.define import DEFAULT_RULES_DIR
from preprocessor import scan_diagnostics


@pytest.fixture
def c_lang(config_loaded):
    """切到 C 语言包（include 策略 = error），用完切回默认包。"""
    del config_loaded
    from core.config_registry import ConfigRegistry

    ConfigRegistry.load_language("grammar/c", plugins_dir="grammar/c/plugins")
    try:
        yield
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


def test_missing_include_yields_hard_diagnostic(c_lang) -> None:
    """C 包：缺头文件 ⇒ `missing` 诊断（不抛异常）。"""
    diags = scan_diagnostics("#include <nope_xyz.h>\nint x;\n", "grammar/c")
    assert [d["kind"] for d in diags] == ["missing"]
    assert "include 文件未找到" in diags[0]["message"]


def test_clean_source_yields_no_diagnostic(c_lang) -> None:
    """无 include 问题 ⇒ 空（不误报）。"""
    assert scan_diagnostics("int x;\n", "grammar/c") == []


def test_verilog_default_policy_keeps_print() -> None:
    """verilog 不声明策略 ⇒ 默认 warn：打印（既有行为）、返回空（A/B 0/144 前提）。"""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        diags = scan_diagnostics('`include "nope.v"\n', DEFAULT_RULES_DIR)
    assert diags == []
    assert "include 文件未找到" in buf.getvalue()


def test_unclosed_define_param_is_controlled(c_lang) -> None:
    """指令 fail-fast（未闭合 `#define` 形参表）转受控诊断，不抛异常。

    判据（两路径统一）：`tpc lint` / `tpc check` 共用本入口 ⇒ 同一条
    `[preprocessor] ...` 报文 + rc=1（此前 CLI 打印 traceback）。
    """
    diags = scan_diagnostics("#define G(a, b\nint x;\n", "grammar/c")
    assert [d["kind"] for d in diags] == ["directive"]
    assert "形参表未闭合" in diags[0]["message"]


def test_linter_api_unclosed_define_is_diagnostic_not_raise(c_lang) -> None:
    """直接调用 linter API 也不该收到 traceback：转 blocking `preprocessor-error`。"""
    from linter.scanner import LinterScanner

    scanner = LinterScanner(rules_dir="grammar/c", ext_dirs=["grammar/c/plugins"])
    diags = scanner.scan("#define G(a, b\nint x;\n")
    assert [d.code for d in diags] == ["preprocessor-error"]
    assert diags[0].blocking and "未闭合" in diags[0].message


def test_pipeline_unclosed_define_is_controlled_error(c_lang) -> None:
    """管线路径（`tpc format`/`tpc expand`）也转受控 `error`，不抛异常。"""
    from tests.e2e.run_pipeline import run_pipeline_on_source

    result = run_pipeline_on_source(
        source="#define G(a, b\nint x;\n", rules_dir="grammar/c", quiet=True
    )
    assert result["success"] is False
    assert "preprocessor" in result["error"] and "未闭合" in result["error"]
