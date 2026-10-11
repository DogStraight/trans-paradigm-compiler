"""P3b M1：raw **资格判定**（替换式试解析 + typedef 命名空间 + 声明顺序）。

三条判据（实现处 docstring 为准）：
  ① `_substitution_trial`：把 `( id )` 的 id 的 token 型临时换成包声明
     `trial_as`，重跑**同一候选集**同一 limit 的试解析，**整句通过**
     （`errs==0 且 consumed==limit-i`）才算；
  ② 命中名 kind ∈ 包声明 `type_name = true` 的 kind（C 只认 `typedef`）；
  ③ `(decl_line, decl_column) <= (use_line, use_column)`（同行按列）。
`eligible = ①∧②∧③`，**只作内部证据**：M1 不接 raw、不摘诊断 ⇒ 用户诊断面逐字节
不变（`--json` 快照 / lint accuracy / diag baseline 另有 e2e 证据）。

反例集（八条）必须全部保持"报真错"：本文件逐条断言诊断条数/码/blocking 与
资格判定为 False。
"""

import pytest

from core.define import DEFAULT_RULES_DIR
from core.errors import ConfigError

C_PACK, C_PLUGINS = "grammar/c", "grammar/c/plugins"

TARGET = "typedef int myint;\nx = (myint)y;\n"

# 八条反例：**加声明前缀**的对抗形态（审计最小复现的形态）
COUNTER_PREFIXED = {
    "反例1 x=(t)y + ;": ("typedef int t;\nx = (t)y + ;\n", 2),
    "反例3 跨行 +": ("typedef int t;\nx = (t)y +\n;\n", 2),
    "反例5 缺分号": ("typedef int t;\nx=(t)y\n", 2),
    "反例6 x=((t))y;": ("typedef int t;\nx=((t))y;\n", 2),
    "反例7 声明在后": ("x=(t)y; typedef int t;\n", 2),
    "反例8 tag 名": ("struct t{}; x=(t)y;\n", 2),
}
# 反例 2/4：位点不产生未收敛记录（有语句特征但无候选/lexer 面）⇒ 天然不 eligible
COUNTER_NO_SITE = {
    "反例2 + (u)z + ;": ("typedef int u;\n+ (u)z + ;\n", 1),
    "反例4 + 未闭合串": ('typedef int t;\n+ "unterminated;\n', 1),
}
# 任务原文的无前缀形态（trivially 不 eligible：名不在 pre_scan）
COUNTER_BARE = {
    "反例1' 无声明": "x = (t)y + ;\n",
    "反例7' 无声明": "x=(t)y;\n",
}


@pytest.fixture
def c_scanner(config_loaded):
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


def _scan(scanner, src):
    return scanner.scan(src), scanner.internal_warnings()


class TestEligibilityTarget:
    """目标句：三条判据全过 ⇒ eligible；**M1 只写证据**（诊断面逐字节不变）。"""

    def test_eligible_with_evidence(self, c_scanner):
        _diags, warns = _scan(c_scanner, TARGET)
        assert len(warns) == 1
        w = warns[0]
        assert w["symbol_dependent"] is True
        assert w["symbol_kinds"] == ["typedef"]
        assert w["order_ok"] is True and w["depth_ok"] is True
        assert (w["decl_line"], w["decl_column"], w["decl_depth"]) == (1, 12, 0)
        assert (w["use_line"], w["use_column"], w["use_depth"]) == (2, 0, 0)
        assert w["trial_ok"] is True
        assert (w["trial_errs"], w["trial_consumed"]) == (0, w["trial_limit"])
        assert w["substitute_type"] == "keyword.int"
        assert w["eligible"] is True

    def test_m2_downgrade_enabled(self, c_scanner):
        """M2 已接（与 raw 同批）：资格位点 region 内的结构类诊断摘成内部 warning。

        ⚠ 安全网 = P4 的 analyze 精确符号面校验（raw 校验不过 ⇒ 报错，不静默）；
        本断言只覆盖 linter 侧摘除面（端到端闭环另有管线测试）。
        """
        diags, warns = _scan(c_scanner, TARGET)
        assert diags == []  # 2 条结构类诊断按窄档摘除
        assert warns[0]["eligible"] is True
        assert warns[0]["downgraded"] is True
        assert warns[0]["suppressed"] == 2


class TestDepthGuard:
    """③ 深度守卫（独立审计 A 类）：块内声明不得给块外使用点发资格。

    守卫前 `void f(void) { typedef int t; }\\nx = (t)y;` 位置先后成立 ⇒ 会被判
    eligible（真错被静默）；守卫后 `decl_depth(1) > use_depth(0)` ⇒ ineligible。
    """

    A_CLASS = "void f(void) { typedef int t; }\nx = (t)y;\n"
    A_NESTED = "{ { typedef int t; } }\nx = (t)y;\n"

    def test_block_local_decl_not_eligible(self, c_scanner):
        diags, warns = _scan(c_scanner, self.A_CLASS)
        assert len(diags) == 2 and all(d.blocking for d in diags)
        w = warns[0]
        assert w["symbol_dependent"] is True
        assert w["order_ok"] is True  # 位置先后**成立**
        assert w["depth_ok"] is False  # 深度守卫拦住
        assert (w["decl_depth"], w["use_depth"]) == (1, 0)
        assert w["eligible"] is False

    def test_nested_block_decl_not_eligible(self, c_scanner):
        diags, warns = _scan(c_scanner, self.A_NESTED)
        assert len(diags) == 2 and all(d.blocking for d in diags)
        w = warns[0]
        assert (w["decl_depth"], w["use_depth"]) == (2, 0)
        assert w["depth_ok"] is False and w["eligible"] is False

    def test_same_scope_still_eligible(self, c_scanner):
        """同深度（顶层声明 + 顶层使用）不受守卫影响 ⇒ 仍 eligible。"""
        _diags, warns = _scan(c_scanner, "typedef int t;\nx = (t)y;\n")
        assert (warns[0]["decl_depth"], warns[0]["use_depth"]) == (0, 0)
        assert warns[0]["depth_ok"] is True
        assert warns[0]["eligible"] is True


class TestShadowingBoundary:
    """**已知边界**：pre_scan 无作用域 ⇒ 遮蔽分不出。

    P3c 前置切片把位点发现面扩到 production 层语句位（函数体/单语句体）后，遮蔽
    用例**变成可达**：`typedef int t;\\nvoid f(void){ int t; x = (t)y; }` 产生的位点
    `eligible=True`——M1 判不出"此处 `t` 已被局部变量遮蔽"。这是**已登记边界**，
    不是回归：M2（raw）**不得只依赖 M1 资格**，必须与 P4（analyzer
    `phase="analyze"` 精确符号面校验）同批落地（见 `linter/linter_architecture.md`）。
    """

    SHADOWED = "typedef int t;\nvoid f(void) { int t; x = (t)y; }\n"

    def test_shadowed_use_site_exists_and_m1_unsound(self, c_scanner):
        diags, warns = _scan(c_scanner, self.SHADOWED)
        assert diags == []  # M2：该位点诊断被摘（安全网 = P4 校验，见下）
        # P3c 前：warns == []（函数体语句位不可达）；P3c 后：位点可达
        assert len(warns) == 1
        w = warns[0]
        assert (w["symbol_names"], w["line"], w["column"]) == (["t"], 2, 22)
        # ⚠ M1 在遮蔽上**不健全**（不是"判对了"）：资格判据各自成立，但符号身份错。
        # M2 后该位点被摘诊断（downgraded=1）⇒ **唯一安全网是 P4 精确符号面校验**：
        # P4 必须判 `t` 此处为局部变量 ⇒ 报错（task-31 的查询负责）。
        assert w["eligible"] is True, "边界变化时必须重新登记（M2 不得只依赖 M1）"
        assert w["downgraded"] is True and diags == []


class TestProductionLevelSites:
    """P3c 前置切片（task-28）：位点发现面扩到 production 层语句位。

    判据 1/2：函数体（`CompoundStmt` 的 `@Stmt*`）与 if/while/for/do 单语句体都要
    产出 `eligible=true` 位点。判据 3/4（本类同批冻结）：这些输入的**用户可见诊断
    逐条不变**——位点只进内部通道（`internal_warnings`）。
    """

    # 位点扩展新增可达的输入：期望 (诊断冻结值, 位点 line/column)
    # 期望 = M2 后实测（诊断, 位点 line/column）。可摘 = 诊断起点落在 site region 内。
    FN_BODY = (
        "typedef int myint;\nvoid f(void) { x = (myint)y; }\n",
        [],
        (2, 15),
    )
    IF_IN_FN = (
        "typedef int myint;\nvoid f(void){ if (c) x = (myint)y; }\n",
        [("phase-statement", 1, 14)],  # 诊断报在**容器起点**、不在 site region ⇒ 不摘
        (2, 21),
    )
    IF_TOP = (
        "typedef int myint;\nif (c) x = (myint)y;\n",
        [],
        (2, 7),
    )
    WHILE_TOP = (
        "typedef int myint;\nwhile (c) x = (myint)y;\n",
        [],
        (2, 10),
    )
    FOR_TOP = (
        "typedef int myint;\nfor (;;) x = (myint)y;\n",
        [],
        (2, 9),
    )
    DO_WHILE_TOP = (
        "typedef int myint;\ndo x = (myint)y; while (c);\n",
        [],
        (2, 3),
    )
    NESTED_FN = (
        "typedef int myint;\nvoid f(void) { if (c) { x = (myint)y; } }\n",
        [("phase-statement", 1, 15)],  # 同上：报在容器起点 ⇒ 不摘
        (2, 24),
    )

    @pytest.mark.parametrize(
        "label",
        [
            "FN_BODY",
            "IF_IN_FN",
            "IF_TOP",
            "WHILE_TOP",
            "FOR_TOP",
            "DO_WHILE_TOP",
            "NESTED_FN",
        ],
    )
    def test_site_eligible_and_diagnostics_frozen(self, c_scanner, label):
        src, expected_diags, use_pos = getattr(self, label)
        diags, warns = _scan(c_scanner, src)
        assert [
            (d.code, d.range[0].line, d.range[0].character) for d in diags
        ] == expected_diags, f"{label}: 用户可见诊断变了"
        hits = [w for w in warns if w["eligible"]]
        assert len(hits) == 1, f"{label}: 应有且仅有 1 个 eligible 位点"
        w = hits[0]
        assert (w["line"], w["column"]) == use_pos, f"{label}: 位点未指向使用点"
        assert w["symbol_names"] == ["myint"]
        assert w["symbol_dependent"] is True
        assert (w["order_ok"], w["depth_ok"], w["trial_ok"]) == (True, True, True)

    def test_fn_true_error_not_eligible(self, c_scanner):
        """函数体内**真语法错**（非符号歧义）不得 eligible（位点可达≠放宽判据）。"""
        diags, warns = _scan(
            c_scanner, "typedef int myint;\nvoid f(void) { x = (1 + )y; }\n"
        )
        assert [d.code for d in diags] == ["phase-statement"]
        assert len(warns) == 1
        assert warns[0]["eligible"] is False and warns[0]["symbol_dependent"] is False

    def test_fn_declared_inside_then_used_eligible(self, c_scanner):
        """函数体内"声明后使用"同深度 ⇒ eligible（深度守卫不误伤同深度）。"""
        diags, warns = _scan(
            c_scanner, "void f(void) { typedef int t; x = (t)y; }\n"
        )
        assert diags == []  # M2：该诊断落在 site region 内 ⇒ 摘除
        hits = [w for w in warns if w["eligible"]]
        assert len(hits) == 1 and (hits[0]["line"], hits[0]["column"]) == (1, 30)
        assert hits[0]["suppressed"] == 1

    def test_builtin_cast_no_site(self, c_scanner):
        """内建转换 `(int)`：不产生位点（无未收敛候选）⇒ 无内部噪音。"""
        diags, warns = _scan(c_scanner, "void f(void) { x = (int)y; }\n")
        assert diags == [] and warns == []


class TestCounterExamples:
    """八条反例逐条：仍报真错、且不 eligible。"""

    @pytest.mark.parametrize("label", sorted(COUNTER_PREFIXED))
    def test_prefixed_counter_ineligible(self, c_scanner, label):
        src, n_diags = COUNTER_PREFIXED[label]
        diags, warns = _scan(c_scanner, src)
        assert len(diags) == n_diags and all(d.blocking for d in diags)
        assert warns, f"{label}: 应仍有未收敛记录（位点存在）"
        assert all(w["eligible"] is False for w in warns)

    @pytest.mark.parametrize("label", sorted(COUNTER_NO_SITE))
    def test_no_site_counter_blocking(self, c_scanner, label):
        src, n_diags = COUNTER_NO_SITE[label]
        diags, warns = _scan(c_scanner, src)
        assert len(diags) == n_diags and all(d.blocking for d in diags)
        assert warns == []  # 位点不产生未收敛记录 ⇒ 天然不进资格档

    @pytest.mark.parametrize("label", sorted(COUNTER_BARE))
    def test_bare_counter_ineligible(self, c_scanner, label):
        diags, warns = _scan(c_scanner, COUNTER_BARE[label])
        assert len(diags) == 2 and all(d.blocking for d in diags)
        assert all(w["symbol_dependent"] is False for w in warns)
        assert all(w["eligible"] is False for w in warns)

    def test_counter1_trial_detail(self, c_scanner):
        """反例1 的资格失败原因是①（试解析不整句通过），不是②③。"""
        _diags, warns = _scan(c_scanner, COUNTER_PREFIXED["反例1 x=(t)y + ;"][0])
        w = warns[0]
        assert (w["symbol_dependent"], w["order_ok"]) == (True, True)
        assert w["trial_ok"] is False
        assert w["trial_consumed"] != w["trial_limit"]

    def test_counter7_order_detail(self, c_scanner):
        """反例7 的资格失败原因是③（同行声明在后：decl 列 > use 列）。"""
        _diags, warns = _scan(c_scanner, COUNTER_PREFIXED["反例7 声明在后"][0])
        w = warns[0]
        assert w["symbol_dependent"] is True
        assert w["order_ok"] is False
        assert (w["decl_line"], w["decl_column"]) > (w["use_line"], w["use_column"])

    def test_counter8_kind_detail(self, c_scanner):
        """反例8 的资格失败原因是②（tag 命名空间不算类型名）。"""
        _diags, warns = _scan(c_scanner, COUNTER_PREFIXED["反例8 tag 名"][0])
        assert all(w["symbol_dependent"] is False for w in warns)


class TestControls:
    """既有行为对照：真语法错/内建转换/同名非 typedef。"""

    def test_true_syntax_error_ineligible(self, c_scanner):
        diags, warns = _scan(c_scanner, "x = (1 + )y;\n")
        assert len(diags) == 3 and all(d.blocking for d in diags)
        assert all(w["eligible"] is False for w in warns)

    def test_builtin_cast_no_warning(self, c_scanner):
        diags, warns = _scan(c_scanner, "x = (int)y;\n")
        assert diags == [] and warns == []

    def test_same_name_non_typedef_ineligible(self, c_scanner):
        diags, warns = _scan(c_scanner, "int myint;\nmyint *b;\n")
        assert diags == []
        assert all(w["eligible"] is False for w in warns)


class TestPackDeclaredSemantics:
    """② 的 kind 语义与 ① 的替换 token 型都来自**包声明**（语言知识在 TOML）。"""

    def test_c_pack_declares_type_name_kind(self, config_loaded):
        del config_loaded
        from core.config_registry import ConfigRegistry
        from lexer import load_pre_scan_config

        ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
        cfg = load_pre_scan_config(C_PACK)
        assert set(cfg["type_name_kinds"]) == {"typedef"}
        assert cfg["trial_as"] == {"typedef": "keyword.int"}
        # tag 命名空间**不**声明为类型名
        assert "tag_struct" not in cfg["type_name_kinds"]

    def test_verilog_declares_no_type_name_kind(self, config_loaded):
        """verilog 未声明 ⇒ 引擎零生效（语料面零回归的结构保证）。"""
        del config_loaded
        from core.config_registry import ConfigRegistry
        from lexer import load_pre_scan_config

        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )
        cfg = load_pre_scan_config(DEFAULT_RULES_DIR)
        assert not cfg["type_name_kinds"]
        assert cfg["trial_as"] == {}

    def test_type_name_without_trial_as_fails_fast(self):
        """包声明 type_name 却没给 trial_as ⇒ ConfigError（不静默降级）。"""
        from lexer.pre_scan import _compile

        with pytest.raises(ConfigError):
            _compile(
                {
                    "decl": {"typedef": {"keyword": "typedef", "type_name": True}},
                    "clean": [],
                }
            )


class TestParallelPositionFace:
    """③ 的行号/列号来自**并行读取面**（既有 pre_scan() 签名/行为不变）。"""

    def test_pre_scan_with_lines_positions(self, config_loaded):
        del config_loaded
        from core.config_registry import ConfigRegistry
        from lexer import load_pre_scan_config, pre_scan
        from lexer.pre_scan import pre_scan_with_lines

        ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
        cfg = load_pre_scan_config(C_PACK)
        src = "/* 注释\n跨行 */\ntypedef int myint;\n"
        kinds = pre_scan(src, cfg)
        recs = pre_scan_with_lines(src, cfg)
        assert kinds == {name: rec["kind"] for name, rec in recs.items()}
        assert recs["myint"] == {
            "kind": "typedef",
            "line": 3,
            "column": 12,
            "depth": 0,
        }

    def test_same_line_order_needs_column(self, config_loaded):
        """同行声明在前/在后只差列：行号不可分（实测反例 7）。"""
        del config_loaded
        from core.config_registry import ConfigRegistry
        from lexer import load_pre_scan_config
        from lexer.pre_scan import pre_scan_with_lines

        ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
        cfg = load_pre_scan_config(C_PACK)
        before = pre_scan_with_lines("typedef int t; x=(t)y;\n", cfg)["t"]
        after = pre_scan_with_lines("x=(t)y; typedef int t;\n", cfg)["t"]
        assert before["line"] == after["line"] == 1
        assert before["column"] < after["column"]
