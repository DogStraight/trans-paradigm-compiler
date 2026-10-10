"""管线侧接线：`_stage_lint` → `_PipelineContext.internal_warnings`（P2a 旁路载体）。

消费链：`LookaheadTable`（Level 2 收敛判定，按次重置）→ `Discovery` →
`LinterScanner.scan()` → `pipeline._stage_lint` → `_PipelineContext`（供后续
"歧义位点 raw 暂缓建树"消费）。**不进**诊断 / `--json` / exit code / 落盘。
"""

import pytest

from core.define import DEFAULT_RULES_DIR


@pytest.fixture
def c_linter(config_loaded):
    """C 包 LinterScanner（用完切回 verilog——语言作用域是全局态）。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    from core.config_registry import ConfigRegistry
    from linter.scanner import LinterScanner

    ConfigRegistry.load_language("grammar/c", plugins_dir="grammar/c/plugins")
    try:
        yield LinterScanner("grammar/c", ext_dirs=["grammar/c/plugins"])
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


def _ctx(source: str, linter):
    """最小 `_PipelineContext`（只填 `_stage_lint` 会读的字段 + 必填位）。"""
    from pipeline import _PipelineContext

    ctx = _PipelineContext(
        source=source,
        input_path=None,
        rules_dir="grammar/c",
        ext_dirs=["grammar/c/plugins"],
        quiet=True,
        stage=None,
        expand_macros=False,
        analyzer_enabled=True,
        transform_enabled=True,
        renderer_enabled=True,
        no_lint=False,
        parse_enabled=True,
        format_output=False,
        expand_enhanced=False,
        include_dirs=None,
        predefined=None,
        undefine=None,
        check_idempotent=False,
    )
    ctx.linter = linter
    ctx.lint_source = source
    return ctx


def test_stage_lint_propagates_internal_warnings(c_linter):
    """未收敛位点从 linter 旁路进 ctx（且 lint 未阻断 → 返回 True）。"""
    from pipeline import _stage_lint

    src = "int myint;\nmyint *b;\n"
    ctx = _ctx(src, c_linter)
    assert _stage_lint(ctx) is True
    warnings = ctx.internal_warnings
    assert len(warnings) == 1
    w = warnings[0]
    assert w["kind"] == "candidate-not-converged"
    assert w["reason"] == "ambiguous_full_match"
    assert (w["line"], w["column"]) == (2, 0)
    assert set(w["tied"]) == {"Declaration", "ExprStmt"}


def test_stage_lint_clean_input_leaves_field_empty(c_linter):
    """收敛输入 ⇒ 字段为空（不产生噪声）。"""
    from pipeline import _stage_lint

    ctx = _ctx("typedef int myint;\nmyint v;\n", c_linter)
    assert _stage_lint(ctx) is True
    assert ctx.internal_warnings == []


def test_no_lint_leaves_field_empty(c_linter):
    """`no_lint` 短路：不扫描 ⇒ 字段保持缺省空列表。"""
    from pipeline import _stage_lint

    ctx = _ctx("int myint;\nmyint *b;\n", c_linter)
    ctx.no_lint = True
    assert _stage_lint(ctx) is True
    assert ctx.internal_warnings == []
