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


# ── P3b M1：资格判定证据 + 八反例诊断冻结（**不接 raw、不摘诊断**） ──

C_PACK, C_PLUGINS = "grammar/c", "grammar/c/plugins"
TARGET = "typedef int myint;\nx = (myint)y;\n"

# 八条反例：期望诊断（码, LSP 行 0-based, 列）——**改前实测冻结**
# （PRE=HEAD 快照测得；`_drafts/verify_task25_zerochange.py` 逐条比对确认未变）
COUNTER_CASES = {
    "反例1": (
        "typedef int t;\nx = (t)y + ;\n",
        [("phase-unrecognized", 1, 0), ("phase-statement", 1, 7)],
    ),
    "反例2": ("typedef int u;\n+ (u)z + ;\n", [("phase-statement", 1, 5)]),
    "反例3": (
        "typedef int t;\nx = (t)y +\n;\n",
        [("phase-unrecognized", 1, 0), ("phase-statement", 1, 7)],
    ),
    "反例4": ('typedef int t;\n+ "unterminated;\n', [("phase-statement", 1, 2)]),
    "反例5": (
        "typedef int t;\nx=(t)y\n",
        [("phase-unrecognized", 1, 0), ("phase-statement", 1, 5)],
    ),
    "反例6": (
        "typedef int t;\nx=((t))y;\n",
        [("phase-unrecognized", 1, 0), ("phase-statement", 1, 7)],
    ),
    "反例7": (
        "x=(t)y; typedef int t;\n",
        [("phase-unrecognized", 0, 0), ("phase-statement", 0, 5)],
    ),
    "反例8": (
        "struct t{}; x=(t)y;\n",
        [("phase-unrecognized", 0, 12), ("phase-statement", 0, 17)],
    ),
    "反例1无声明": (
        "x = (t)y + ;\n",
        [("phase-unrecognized", 0, 0), ("phase-statement", 0, 7)],
    ),
    "反例7无声明": (
        "x=(t)y;\n",
        [("phase-unrecognized", 0, 0), ("phase-statement", 0, 5)],
    ),
}


@pytest.fixture
def c_lang(config_loaded):
    """切到 C 包跑管线（用完切回 verilog——语言作用域是全局态）。"""
    del config_loaded  # fixture 依赖声明（配置加载）
    from core.config_registry import ConfigRegistry

    ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
    try:
        yield
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


def _run(src: str) -> dict:
    from pipeline import run_pipeline_on_source

    return run_pipeline_on_source(
        source=src,
        input_path="case.c",
        out_dir=None,
        quiet=True,
        rules_dir=C_PACK,
        ext_dirs=[C_PLUGINS],
    )


class TestM1DiagnosticsFrozen:
    """M1 交付面：资格判定**只写内部证据**，用户诊断面逐条冻结（目标句也仍 blocking）。

    M2（raw + 窄档摘诊断）与 P4 原子落地，见 `linter/linter_architecture.md`。
    """

    def test_target_eligible_but_still_blocking(self, c_lang):
        from linter.scanner import LinterScanner

        scanner = LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
        diags = scanner.scan(TARGET)
        assert [d.code for d in diags] == ["phase-unrecognized", "phase-statement"]
        assert all(d.blocking for d in diags)
        warns = scanner.internal_warnings()
        assert warns[0]["eligible"] is True
        assert "downgraded" not in warns[0]

        res = _run(TARGET)
        assert res.get("success") is False
        assert res.get("error") == "lint failed: 2 error(s)"


class TestCounterExamplesStillBlocking:
    """八条反例（+ 无声明形态）：诊断逐条冻结、管线仍失败——**门禁不得放宽**。"""

    @pytest.mark.parametrize("label", sorted(COUNTER_CASES))
    def test_counter_reports_real_error(self, c_lang, label):
        src, expected = COUNTER_CASES[label]
        from linter.scanner import LinterScanner

        scanner = LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
        diags = scanner.scan(src)
        got = [(d.code, d.range[0].line, d.range[0].character) for d in diags]
        assert got == expected, f"{label}: 诊断面变了（真错被吞？）"
        assert all(d.blocking for d in diags)
        assert all(w["eligible"] is False for w in scanner.internal_warnings())

        res = _run(src)
        assert res.get("success") is False
        assert res.get("error", "").startswith("lint failed")


class TestControlsUnaffected:
    """对照：真语法错/内建转换/同名非 typedef 行为不变。"""

    def test_true_syntax_error(self, c_lang):
        res = _run("x = (1 + )y;\n")
        assert res.get("success") is False
        assert res.get("error") == "lint failed: 3 error(s)"

    def test_builtin_cast(self, c_lang):
        res = _run("x = (int)y;\n")
        assert res.get("success") is True

    def test_same_name_non_typedef(self, c_lang):
        res = _run("int myint;\nmyint *b;\n")
        assert res.get("success") is True
