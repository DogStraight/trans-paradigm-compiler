"""tests/languages/c/test_c_storage_class_checks.py — C 存储类语义约束（CSC001–CSC012）判据。

被测：`grammar/c/plugins/checks/storage_class/`（本包**首个 check 组件**）——
规则表 `rules/storage.toml`（id/kind/severity/default/message）+ L2 handler
`rules/_storage_check.py`，输入面 = 包侧 capture 挂的符号 attrs（`sc`/`fs`/`is_function`/
`has_init`/声明起点）。

判据覆盖 task-36 的 7 条：
  1. 每条约束的正/负样本逐条（负：报 + warning + 位置；正：不报）
  2. 真实语料零误报（附命令与计数）
  3. 语法宽进不回归（负样本仍能解析出 AST；新增诊断不含 error ⇒ 管线 success 面不变）
  4. 多声明符去重（`static extern int a, b;` 只报 1 条）
  5. 缺陷态变红见 `tools/check_gate_efficacy.py --list` 的 CSC 变异（去掉例外表 / 去掉去重）
  6. 按影响范围测试（命令见报告）
  7. pyright strict（本文件与 handler）0

**CSC001 禁止朴素计数**（Lead 硬要求）：`static inline int f(void){}` 是头文件高频**合法**形态，
必须在**全部规则启用**下也不报（`test_csc001_forbids_naive_counting`）。
"""

import os
from pathlib import Path

import pytest

from analyzer.traversal import AnalysisTraversal
from core.check_registry import get_check_rules
from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from transform.normalizer import normalize_ast

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")

#: 负样本（非法组合）⇒ 期望命中的诊断码（一条输入可能同时命中多条真违规）
NEGATIVE: dict[str, tuple[str, tuple[str, ...]]] = {
    "typedef+static": ("typedef static int x;\n", ("CSC002",)),
    "static+extern": ("static extern int x;\n", ("CSC001",)),
    "三存储类": ("static extern _Thread_local int x;\n", ("CSC001",)),
    "_Thread_local+auto": ("void f(void){ _Thread_local auto int x; }\n", ("CSC001", "CSC003")),
    "_Thread_local 用于函数": ("static _Thread_local int f(void);\n", ("CSC004",)),
    "constexpr 无初始化器": ("constexpr int n;\n", ("CSC008",)),
    "constexpr 用于函数": ("constexpr int f(void) { return 1; }\n", ("CSC007",)),
    "inline 用于对象": ("inline int x;\n", ("CSC012",)),
    "_Noreturn 用于对象": ("_Noreturn int x;\n", ("CSC012",)),
    "auto 文件域": ("auto int x;\n", ("CSC009",)),
    "register 文件域": ("register int x;\n", ("CSC010",)),
    "register 用于函数": ("register int f(void);\n", ("CSC011",)),
}

#: 正样本（合法形态）⇒ **全部规则启用**下也不得报（含关键的头文件形态 `static inline`）
POSITIVE: dict[str, str] = {
    "static int": "static int x;\n",
    "static inline 函数（关键）": "static inline int f(void) { return 1; }\n",
    "inline 函数": "inline int f(void) { return 1; }\n",
    "_Noreturn 函数": "_Noreturn void g(void);\n",
    "static _Thread_local": "static _Thread_local int t;\n",
    "extern _Thread_local": "extern _Thread_local int t;\n",
    "c23 thread_local + static": "static thread_local int t;\n",
    "块内 _Thread_local": "void f(void){ _Thread_local int t; }\n",
    "块内 auto/register": "void f(void){ auto int a; register int b; }\n",
    "constexpr 有初始化器": "constexpr int n = 4;\n",
    "static constexpr": "static constexpr int n = 4;\n",
    "typedef 单独": "typedef int myint;\n",
    "无存储类": "int x;\n",
}

#: 真实语料（误报面判据）
CORPUS_DIRS = ("tests/languages/c/samples", "tests/engine/linter/corpus_raw")


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """C 包（含增量组件与 check 组件）；结束恢复 verilog。"""
    del config_loaded
    ConfigRegistry.load_language(_RULES, plugins_dir=_PLUGINS)
    rules = setup_grammar(_RULES, GrammarRulesRegister(), ext_dirs=[_PLUGINS])
    stmt = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=_RULES, rules=rules, rule_selector=RuleSelector(rules, stmt), log_file=""
    )
    lexer = Lexer(rules_dir=_RULES, ext_dirs=[_PLUGINS])
    yield {"rules": rules, "parser": parser, "lexer": lexer}
    ConfigRegistry.load_language(
        "grammar/verilog", plugins_dir="grammar/verilog/plugins"
    )


def _all_ids() -> list[str]:
    return [str(r["id"]) for r in get_check_rules(plugins_dir=_PLUGINS)]


def _analyze(c_env, src: str, *, enabled: list[str] | None = None) -> tuple[AnalysisTraversal, list]:
    """解析 → normalize（生产口径）→ analyze；返回 (traversal, CSC 诊断)。"""
    ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
    assert ast is not None, f"语法层应宽进接受：{src!r}"
    at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
    if enabled is not None:
        at._checks_enabled = list(enabled)
    at.analyze(normalize_ast(ast))
    return at, [d for d in at.diagnostics if str(d.code).startswith("CSC")]


class TestNegativeSamples:
    """判据 1（负样本）：非法组合 ⇒ 报对应码 + warning + 位置可查。"""

    @pytest.mark.parametrize("case", list(NEGATIVE))
    def test_violation_reported(self, c_env, case):
        src, expected = NEGATIVE[case]
        at, diags = _analyze(c_env, src, enabled=_all_ids())
        codes = {d.code for d in diags}
        assert set(expected) <= codes, f"{case}: 期望 {expected}，实得 {codes}"
        for d in diags:
            if d.code in expected:
                assert d.level == "warning", (case, d.level)
                assert d.node is not None and getattr(d.node, "_pos_line", None) == 1, (
                    case,
                    d.node,
                )
        # 语法宽进不回归：解析成功 + **无 error 级诊断**（warning 不阻断管线 ⇒ success 面不变）
        # ⚠ `AnalysisTraversal.has_errors` 的语义是"有任何诊断"（含 warning），故这里按 level 判。
        errors = [d for d in at.diagnostics if d.level == "error"]
        assert errors == [], (case, errors)

    def test_multi_declarator_reports_once(self, c_env):
        """判据 4：`static extern int a, b;` 两个符号同一声明 ⇒ 只报 1 条。"""
        _, diags = _analyze(c_env, "static extern int a, b;\n", enabled=_all_ids())
        assert [d.code for d in diags] == ["CSC001"], diags

    def test_same_declaration_on_same_line_still_distinct(self, c_env):
        """边界：同一行的**两条**违规声明各报一次（去重键含声明起点列）。"""
        _, diags = _analyze(
            c_env, "static extern int a; static extern int b;\n", enabled=_all_ids()
        )
        assert [d.code for d in diags] == ["CSC001", "CSC001"], diags


class TestPositiveSamples:
    """判据 1（正样本）：合法形态 ⇒ 全部规则启用下也不报。"""

    @pytest.mark.parametrize("case", list(POSITIVE))
    def test_legal_form_not_reported(self, c_env, case):
        _, diags = _analyze(c_env, POSITIVE[case], enabled=_all_ids())
        assert diags == [], (case, diags)

    def test_csc001_forbids_naive_counting(self, c_env):
        """Lead 硬要求：`static inline int f(void){}`（sc=[static]、fs=[inline]）不得误报。"""
        at, diags = _analyze(
            c_env, "static inline int f(void) { return 1; }\n", enabled=_all_ids()
        )
        assert diags == [], diags
        # 取证：符号 attrs 确实是"1 个存储类 + 1 个函数说明符"
        sym = at.all_symbols[0]
        assert sym.attrs["sc"] == ["static"] and sym.attrs["fs"] == ["inline"], sym.attrs
        assert sym.attrs["is_function"] is True

    def test_csc001_no_naive_counting_on_fs_pairs(self, c_env):
        """朴素计数（sc+fs 一起数）会把 `inline int x;` 同时报 CSC001+CSC012；

        正确行为：**只报 CSC012**（函数说明符不是存储类）。
        """
        _, diags = _analyze(c_env, "inline int x;\n", enabled=_all_ids())
        assert [d.code for d in diags] == ["CSC012"], [str(d) for d in diags]

    def test_csc001_handler_ignores_function_specifiers(self):
        """handler 单元判据：`sc=[static]` + `fs=[inline]` ⇒ CSC001 通过（禁止朴素计数）。"""

        class _Sym:
            name = "f"
            kind = "variable"
            attrs = {
                "sc": ["static"],
                "fs": ["inline"],
                "is_function": False,
                "has_init": False,
                "decl_start_line": 1,
                "decl_start_col": 0,
            }

        class _Ctx:
            extra: dict = {}

        from grammar.c.plugins.checks.storage_class.rules._storage_check import check_storage

        assert check_storage(_Sym(), {"id": "CSC001"}, _Ctx()) is None

    def test_constexpr_combinations_are_permitted(self, c_env):
        """C23 `constexpr` 共现规则未核实 ⇒ CSC001/CSC002 保守放行（宁可漏报不误报）。"""
        for src in ("static constexpr int n = 4;\n", "constexpr int n = 4;\n"):
            _, diags = _analyze(c_env, src, enabled=_all_ids())
            assert diags == [], (src, diags)


class TestDefaultSwitch:
    """判据：默认开关按"条款档位"（Lead 拍板 ①②）——A 档默认开、B 档 opt-in。"""

    def test_rule_defaults(self):
        table = {
            str(r["id"]): bool(r.get("default", True))
            for r in get_check_rules(plugins_dir=_PLUGINS)
            if str(r["id"]).startswith("CSC")
        }
        assert table == {
            "CSC001": True,
            "CSC002": True,
            "CSC003": True,
            "CSC004": False,
            "CSC007": False,
            "CSC008": False,
            "CSC009": False,
            "CSC010": False,
            "CSC011": False,
            "CSC012": False,
        }, table

    def test_default_pass_only_reports_a_tier_codes(self, c_env):
        """默认档只出 A 档码（CSC001/002/003）；B 档输入在默认档静默（opt-in）。"""
        for case, (src, _expected) in NEGATIVE.items():
            _, diags = _analyze(c_env, src)
            codes = {d.code for d in diags}
            if codes:
                assert codes <= {"CSC001", "CSC002", "CSC003"}, (case, codes)

    def test_disabled_rules_do_not_fire(self, c_env):
        """显式启用集不含某规则 ⇒ 该码不出现（"不选即关"）。"""
        _, diags = _analyze(c_env, "auto int x;\n", enabled=["CSC001"])
        assert diags == [], diags


class TestCorpusFalsePositives:
    """判据 2：真实语料零误报（default 档与 all 档都测）。"""

    def _corpus(self) -> list[Path]:
        files: list[Path] = []
        for base in CORPUS_DIRS:
            p = Path(base)
            if p.is_dir():
                files.extend(sorted(f for f in p.rglob("*") if f.suffix in (".c", ".h")))
        return files

    def test_corpus_zero_false_positives(self, c_env):
        files = self._corpus()
        assert files, "语料清单为空——判据失效"
        for enabled in (None, _all_ids()):
            for path in files:
                src = path.read_text(encoding="utf-8")
                ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
                if ast is None:  # 既有语料里本就有 lint 拒的样本，与本节无关
                    continue
                at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
                if enabled is not None:
                    at._checks_enabled = list(enabled)
                at.analyze(normalize_ast(ast))
                csc = [d for d in at.diagnostics if str(d.code).startswith("CSC")]
                assert csc == [], (str(path), enabled is not None, [str(d) for d in csc])
