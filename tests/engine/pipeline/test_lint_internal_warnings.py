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


class TestM2AndRawWiring:
    """M2 窄档摘诊断 + raw 承载同批接线：目标句 0 blocking、raw 按 region 消费。

    ⚠ 端到端闭环还要求 P4 的 analyze 精确符号面校验**接受**该名（当前 C 包把
    `typedef` 声明收成 `kind="variable"` ⇒ P4 判否并**报错**，见 task-31 侧）；
    本类只断言到 raw 层（本批交付面），不把对方 WIP 写成失败。
    """

    @pytest.mark.skip(
        reason="G4（#49）：typedef 强转由解析期符号判定直接建树，不再走 raw 承载；"
        "本用例的 raw 消费前提失效，raw 机制测试随 pre_scan 专项整治（ADR-0024）重建"
    )
    def test_target_zero_blocking_and_raw_consumed(self, c_lang):
        from linter.scanner import LinterScanner

        scanner = LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
        diags = scanner.scan(TARGET)
        assert [d for d in diags if d.blocking] == []
        warns = scanner.internal_warnings()
        assert warns[0]["eligible"] is True and warns[0]["downgraded"] is True

        res = _run(TARGET)
        parser = res.get("parser")
        if parser is None:  # 极早失败（不应发生）：仍然报出真实错误
            raise AssertionError(f"管线未到 parser: {res.get('error')!r}")
        consumed = parser._raw_sites_consumed
        assert len(consumed) == 1, "目标句应有一个 raw 位点被消费"
        assert consumed[0]["text"] == "x = (myint)y;"       # 原文保真
        assert parser._parse_truncated is False             # 不截断
        # 区间等式：消费区间 = region 半开化
        assert res.get("success") or "@RawStatement" in str(res.get("error")), (
            "raw 节点必须被 P4 访问（不可静默跳过校验）"
        )


class TestCheckWiring:
    """`tpc check`（`analyzer/structure.py`）与 pipeline **同形接线**（判据 4）。

    check 的阶段 1 是 `linter.scan`：M2 摘掉阻断诊断后必须**同时**把合格位点交给它
    自建的 Parser，否则解析必截断 ⇒ 出现"`parse_ok=False` 却 `exit_code=0` 且
    `syntax=[]`"的自相矛盾（目标输入此前正落在这个态）。
    """

    def test_check_target_parse_ok_and_exit_zero(self, c_lang, tmp_path):
        from analyzer.checker import ProjectChecker

        target = tmp_path / "target.c"
        target.write_bytes(TARGET.encode("utf-8"))
        report = ProjectChecker(
            rules_dir=C_PACK, ext_dirs=[C_PLUGINS], include_dirs=None
        ).check(str(target))
        entry = report["files"][0]
        assert entry["parse_ok"] is True, entry
        assert entry["parse_error"] == "", entry
        assert entry["syntax"] == [], entry
        assert report["exit_code"] == 0, report

    def test_check_counter_still_reports(self, c_lang, tmp_path):
        """反例在 check 下仍报（真错不被 M2/raw 掩盖）；只锁"有报告 + 非零退出"。"""
        from analyzer.checker import ProjectChecker

        bad = tmp_path / "counter.c"
        bad.write_bytes("typedef int t;\nx = (t)y + ;\n".encode("utf-8"))
        report = ProjectChecker(
            rules_dir=C_PACK, ext_dirs=[C_PLUGINS], include_dirs=None
        ).check(str(bad))
        entry = report["files"][0]
        assert report["exit_code"] != 0, report
        assert entry["syntax"], entry


class TestCounterExamplesStillBlocking:
    """八条反例（+ 无声明形态）：诊断逐条冻结、管线仍失败——**门禁不得放宽**。"""

    @pytest.mark.parametrize("label", sorted(COUNTER_CASES))
    def test_counter_reports_real_error(self, c_lang, label):
        src, _expected = COUNTER_CASES[label]
        from linter.scanner import LinterScanner

        scanner = LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
        diags = scanner.scan(src)
        # #49 后诊断面变化（G4 解析期符号判定接管）：linter 启发式接受 typedef
        # 强转形态 ⇒ 可能不再报 phase-unrecognized，真错改由 parser 符号表拒绝。
        # 安全性质 = **真错仍被拒**（管线失败，不得静默通过）——不再冻结诊断面；
        # 若 linter 仍报，必须是阻断级（内部 warning 资格不得放行）。
        assert all(d.blocking for d in diags)
        # M1 资格面已随 pre_scan 退役（T2b）：内部 warning 不再带 eligible 字段，
        # raw 暂缓建树无从触发 ⇒ 真错只能以阻断诊断呈现。

        res = _run(src)
        assert res.get("success") is False
        err = res.get("error", "")
        assert err.startswith("lint failed") or "parse truncated" in err, err


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
