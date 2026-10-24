"""tests/languages/c/test_c_type_semantics_checks.py — C tag 与枚举常量语义（TAG001/TAG002/ENUM001–003）判据。

被测：`grammar/c/plugins/checks/type_semantics/`（C 包第二个 check 组件）——
规则表 `rules/types.toml`（id/kind/severity/default/message + 头注条款引文与档位）+
L2 handler `rules/_tag_check.py`，输入面 = 包侧 `tag_capture` 挂的符号 attrs（`tag_kind`/`has_body`/
`has_complete_type`（C23 固定底层类型枚举，循环 #42）/ 声明起点）+ 同作用域符号表 `scope.symbols`。

判据覆盖 task-38 的 7 条：
  1. 正样本（不报）：前向+定义、引用+定义、内层同名 tag、跨作用域同名枚举常量、8 语料 default+all 两档 0 条
  2. 负样本（报 + warning + 位置）：TAG001/TAG002/ENUM001 各 1 条；三次定义仍只报 1 条
  3. **TAG001 反例（硬要求）**：`struct ring; struct ring *p; struct ring { int a; };` ⇒ 0 报
     （naive"同 tag ≥2 次即报"实测会一次误报 24 条：语料 9 条带体定义 + 24 条无体引用）
  4. 语法宽进不回归：负样本仍解析 + 无 error 级诊断
  5. 缺陷态变红见 `tools/check_gate_efficacy.py --list` 的 TAG 变异（去"双方带体" / 去作用域判定）
  6. 按影响范围测试（命令见报告）
  7. pyright strict（本文件与 handler）0
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
_PREFIXES = ("TAG", "ENUM")

#: 负样本（非法）⇒ 期望命中的诊断码
NEGATIVE: dict[str, tuple[str, tuple[str, ...]]] = {
    "TAG001 两次带体": ("struct S { int a; };\nstruct S { int b; };\n", ("TAG001",)),
    "TAG001 union 两次带体": ("union U { int a; };\nunion U { float b; };\n", ("TAG001",)),
    "TAG002 struct→union": ("struct S;\nunion S;\n", ("TAG002",)),
    "TAG002 struct→enum": ("struct S { int a; };\nenum S { X };\n", ("TAG001", "TAG002")),
    "ENUM003 裸 enum 前向": ("enum E;\nenum E { A };\n", ("ENUM003",)),
    "ENUM003 永不完整": ("enum E;\n", ("ENUM003",)),
    "ENUM001 同表重名": ("enum E { A, A };\n", ("ENUM001",)),
    "ENUM001 跨表同作用域": ("enum E1 { A };\nenum E2 { A };\n", ("ENUM001",)),
    "ENUM002 反向": ("enum { A };\nint A;\n", ("ENUM002",)),
}

#: 正样本（合法）⇒ **全部规则启用**下也不得报
POSITIVE: dict[str, str] = {
    "前向+定义": "struct ring;\nstruct ring { int a; };\n",
    "引用+定义（硬要求）": "struct ring;\nstruct ring *p;\nstruct ring { int a; };\n",
    "纯引用多次": "struct ring *a;\nstruct ring *b;\nstruct ring *c;\n",
    "定义+引用": "struct ring { int a; };\nstruct ring *p;\n",
    "定义+指针引用": "struct S { int a; };\nstruct S *p;\nstruct S *q;\n",
    "内层同名 tag": "struct S { int a; };\nvoid f(void){ struct S { int b; }; }\n",
    "跨作用域枚举常量": "enum { A };\nvoid f(void){ enum { A }; }\n",
    "不同 tag 的枚举常量": "enum E1 { A };\nenum E2 { B };\n",
    "struct 与 union 不同 tag": "struct S { int a; };\nunion U { int b; };\n",
    "枚举定义后引用": "enum E { A };\nenum E;\n",
    "外层完整 enum 的块内引用": "enum E { A };\nvoid f(void){ enum E; }\n",
    # C23 §6.7.2.2：带固定底层类型的枚举**总是完整**（`enum E : int;` 是合法的
    # 不透明枚举声明）⇒ ENUM003 必须豁免（循环 #42；ADR-0021 行 6 的触发条件）
    "C23 固定底层类型枚举（带体）": "enum E : int { A };\n",
    "C23 固定底层类型枚举（不透明声明）": "enum E : int;\n",
    "C23 固定底层类型后的裸引用": "enum E : int;\nenum E;\n",
    "枚举常量与 tag 同名": "enum { A };\nstruct A { int x; };\n",
    "同一 struct 多次引用": "struct S;\nstruct S *f(void);\nstruct S *g(void);\n",
}

CORPUS_DIRS = ("tests/languages/c/samples", "tests/engine/linter/corpus_raw")


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """C 包（含增量组件与两个 check 组件）；结束恢复 verilog。"""
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
    ConfigRegistry.load_language("grammar/verilog", plugins_dir="grammar/verilog/plugins")


def _all_ids() -> list[str]:
    return [str(r["id"]) for r in get_check_rules(plugins_dir=_PLUGINS)]


def _analyze(c_env, src: str, *, enabled: list[str] | None = None) -> tuple[AnalysisTraversal, list]:
    """解析 → normalize（生产口径）→ analyze；返回 (traversal, TAG/ENUM 诊断)。"""
    ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
    assert ast is not None, f"语法层应宽进接受：{src!r}"
    at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
    if enabled is not None:
        at._checks_enabled = list(enabled)
    at.analyze(normalize_ast(ast))
    return at, [d for d in at.diagnostics if str(d.code).startswith(_PREFIXES)]


class TestPositiveSamples:
    """判据 1/3：合法形态（含"引用 + 定义"硬要求）⇒ 全规则启用下 0 报。"""

    @pytest.mark.parametrize("case", list(POSITIVE))
    def test_legal_form_not_reported(self, c_env, case):
        _, diags = _analyze(c_env, POSITIVE[case], enabled=_all_ids())
        assert diags == [], (case, diags)

    def test_tag001_reference_then_definition_no_report(self, c_env):
        """**硬要求**：引用/前向声明 + 一次带体定义 ⇒ 0 报（naive 实现会误报）。"""
        src = "struct ring;\nstruct ring *p;\nstruct ring { int a; };\n"
        at, diags = _analyze(c_env, src, enabled=_all_ids())
        assert diags == [], diags
        tags = [s for s in at.all_symbols if s.kind == "tag"]
        assert len(tags) == 3, [(s.name, s.attrs) for s in tags]
        assert [bool(s.attrs.get("has_body")) for s in tags] == [False, False, True], [
            s.attrs for s in tags
        ]

    def test_pure_references_no_report(self, c_env):
        """纯引用多次（实测语料里最多的一类）⇒ 0 报。"""
        src = "struct ring *a;\nstruct ring *b;\nstruct ring *c;\n"
        _, diags = _analyze(c_env, src, enabled=_all_ids())
        assert diags == [], diags

    def test_tag_namespace_is_separate(self, c_env):
        """tag 命名空间独立：枚举常量与同名 tag 不冲突。"""
        _, diags = _analyze(c_env, "enum { A };\nstruct A { int x; };\n", enabled=_all_ids())
        assert diags == [], diags

    def test_enum003_c23_fixed_underlying_type_is_exempt(self, c_env):
        """C23 固定底层类型 ⇒ 恒完整 ⇒ ENUM003 不报（ADR-0021 行 6 的豁免，循环 #42）。

        判据取**符号 attrs**（`has_complete_type` 由 `tag_capture.complete_path` 提供）
        与诊断面两处：attr 缺失时诊断会误报（本轮缺陷态实测 1 条），故两处都要断。
        """
        src = "enum E : int;\n"
        at, diags = _analyze(c_env, src, enabled=_all_ids())
        assert diags == [], [str(d) for d in diags]
        tags = [s for s in at.all_symbols if s.kind == "tag"]
        assert len(tags) == 1, [(s.name, s.attrs) for s in tags]
        assert tags[0].attrs.get("has_body") is False, tags[0].attrs
        assert tags[0].attrs.get("has_complete_type") is True, tags[0].attrs


class TestNegativeSamples:
    """判据 2：非法形态 ⇒ 报对应码 + warning + 位置可查。"""

    @pytest.mark.parametrize("case", list(NEGATIVE))
    def test_violation_reported(self, c_env, case):
        src, expected = NEGATIVE[case]
        at, diags = _analyze(c_env, src, enabled=_all_ids())
        codes = {d.code for d in diags}
        assert set(expected) <= codes, f"{case}: 期望 {expected}，实得 {codes}"
        for d in diags:
            if d.code in expected:
                assert d.level == "warning", (case, d.level)
                assert d.node is not None, case
                assert getattr(d.node, "_pos_line", None) is not None, (case, d.node)
        errors = [d for d in at.diagnostics if d.level == "error"]
        assert errors == [], (case, errors)

    def test_second_definition_position(self, c_env):
        """位置沿用 `sym.decl_node`（第二个 tag 的标识符）⇒ 行号指向第二处定义。"""
        _, diags = _analyze(
            c_env, "struct S { int a; };\nstruct S { int b; };\n", enabled=_all_ids()
        )
        assert [d.code for d in diags] == ["TAG001"], diags
        assert getattr(diags[0].node, "_pos_line", None) == 2, diags[0].node

    def test_three_definitions_report_once(self, c_env):
        """按 (规则, 名, 作用域) 去重：三次带体定义仍只报 1 条。"""
        src = "struct S { int a; };\nstruct S { int b; };\nstruct S { int c; };\n"
        _, diags = _analyze(c_env, src, enabled=_all_ids())
        assert [d.code for d in diags] == ["TAG001"], [str(d) for d in diags]

    def test_same_name_different_scopes_not_merged(self, c_env):
        """同一 tag 在两个函数里各自定义 ⇒ 不同作用域，不报。"""
        src = (
            "void f(void){ struct S { int a; }; }\n"
            "void g(void){ struct S { int b; }; }\n"
        )
        _, diags = _analyze(c_env, src, enabled=_all_ids())
        assert diags == [], diags


class TestDefaultSwitchByClauseTier:
    """default 按条款档位自动定（Lead 拍板 ①）：A 档原文 ⇒ true；脚注档 ⇒ false。"""

    def test_rule_defaults(self):
        table = {
            str(r["id"]): bool(r.get("default", True))
            for r in get_check_rules(plugins_dir=_PLUGINS)
            if str(r["id"]).startswith(_PREFIXES)
        }
        assert table == {
            "TAG001": True,
            "TAG002": True,
            "ENUM003": True,
            "ENUM001": False,
            "ENUM002": False,
        }, table

    def test_enum_rules_are_opt_in(self, c_env):
        """脚注档规则默认静默、显式启用后报（opt-in 语义）。"""
        for src, code in (
            ("enum E { A, A };\n", "ENUM001"),
            ("enum { A };\nint A;\n", "ENUM002"),
        ):
            _, default = _analyze(c_env, src)
            assert default == [], (src, default)
            _, allr = _analyze(c_env, src, enabled=_all_ids())
            assert [d.code for d in allr] == [code], (src, [str(d) for d in allr])

    def test_a_tier_rules_on_by_default(self, c_env):
        for src, code in (
            ("struct S { int a; };\nstruct S { int b; };\n", "TAG001"),
            ("struct S;\nunion S;\n", "TAG002"),
            ("enum E;\n", "ENUM003"),
        ):
            _, diags = _analyze(c_env, src)
            assert [d.code for d in diags] == [code], (src, [str(d) for d in diags])


class TestCorpusFalsePositives:
    """判据 1：真实语料零误报（default 档与 all 档都测）。"""

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
                hits = [d for d in at.diagnostics if str(d.code).startswith(_PREFIXES)]
                assert hits == [], (str(path), enabled is not None, [str(d) for d in hits])
