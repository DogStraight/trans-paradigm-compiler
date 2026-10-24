"""tests/languages/c/test_c_label_checks.py — C 标签与 switch 标签语义（LAB001–LAB003）判据。

被测：`grammar/c/plugins/checks/labels/`（C 包第三个 check 组件，**形态 = postpass 走 AST**）——
`tpc.toml` 声明 `[[analyzer.postpasses]] run = "rules/_label_check.py:run_label_checks"`；
规则数据 `rules/labels.toml`（id/severity/default/message + 条款引文）；判定 `rules/_label_check.py`
（AST 入口 `analyzer._ast`；规则激活集 `analyzer.checks.active_rule_ids`）。

判据覆盖 task-41 的 7 条：
  1. 正样本（不报）：不同函数同名 label、嵌套块 label+外层 goto、前向 goto、label 与变量同名、
     switch 内 case/default（含 Duff's device）、8 C 语料 default/all 两档 0 条
  2. 负样本（报 + warning + 位置）：重复 label（3 处 ⇒ 2 条，拍板 ②）、未定义 goto、跨函数 goto、
     case/default 无 switch
  3. **语料零误报（硬要求）**：`ring_buffer.c`（FuncDef 9 / LabelStmt 1 / GotoStmt 1 / CaseLabel 2 /
     DefaultLabel 1）**必须 0 报**——只收 `LabelStmt` 才做得到
  4. 语法宽进不回归：负样本仍解析 + 无 error 级诊断
  5. 缺陷态变红见 `tools/check_gate_efficacy.py --list` 的 labels 变异（把 case/default 当普通 label / 去掉两遍扫描）
  6. 按影响范围测试（命令见报告）
  7. pyright strict（本文件与 postpass）0
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
LAB_IDS = ("LAB001", "LAB002", "LAB003")

#: 正样本（合法）⇒ **全部 LAB 规则启用**下 0 报
POSITIVE: dict[str, str] = {
    "不同函数同名 label": "void f(void){ done: ; }\nvoid g(void){ done: ; }\n",
    "嵌套块 label+外层 goto": "void f(void){ { lab: ; }\n goto lab; }\n",
    "前向 goto": "void f(void){ goto done;\n done: ; }\n",
    "label 与变量同名": "void f(void){ int lab; lab: ; }\n",
    "switch 内 case/default": (
        "void f(int n){ switch(n){ case 0: break;\n case 2: break;\n default: break; } }\n"
    ),
    "Duff 形态（switch→do/while→case）": (
        "void f(int n){ switch(n){ case 1: do { n--; case 2: ; } while (n>0); } }\n"
    ),
    "case 在 switch 的 if 块内": "void f(int n){ switch(n){ if (n) { case 1: ; } } }\n",
    "label 未使用": "void f(void){ lab: ; }\n",
    "同函数多个不同 label": "void f(void){ a: ; b: ; goto a; }\n",
    "goto 到同块内 label": "void f(void){ { lab: ; goto lab; } }\n",
    "合法 label+goto": "void f(void){ lab: ; goto lab; }\n",
}

#: 负样本（非法）⇒ 期望 (码, 条数)
NEGATIVE: dict[str, tuple[str, str, int]] = {
    "重复 label 两处": ("void f(void){ lab: ; lab: ; }\n", "LAB001", 1),
    "重复 label 三处": ("void f(void){ lab: ; lab: ; lab: ; }\n", "LAB001", 2),
    "未定义 goto": ("void f(void){ goto nope; }\n", "LAB002", 1),
    "跨函数 goto": ("void g(void){ lab: ; }\nvoid f(void){ goto lab; }\n", "LAB002", 1),
    "case 无 switch": ("void f(void){ case 1: ; }\n", "LAB003", 1),
    "default 无 switch": ("void f(void){ default: ; }\n", "LAB003", 1),
    "两个函数各自重复": (
        "void f(void){ lab: ; lab: ; }\nvoid g(void){ lab: ; lab: ; }\n",
        "LAB001",
        2,
    ),
}

CORPUS_DIRS = ("tests/languages/c/samples", "tests/engine/linter/corpus_raw")


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """C 包（含增量组件与三个 check 组件，其中 labels 走 postpass）；结束恢复 verilog。"""
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


def _ensure_components() -> None:
    """逐测试重新装载语言组件。

    ⚠ `core.plugin_loader._loaded_components` 是**测试级全局态**（`tests/conftest.py::_restore_global_state`
    逐测试还原）⇒ 模块级 fixture 装载的组件在第二个测试开始前已被还原（实测症状：`postpass_trace`
    只剩 `check_rules`，postpass 不再执行、诊断全空；`ConfigRegistry.load_language` 因语言安装态仍
    在而不会重复装载组件）。本片判定依赖 **postpass 组件**，故每个测试显式
    `load_all_components(_PLUGINS)`（组件模块在 `sys.modules` 中复用，代价小）。
    """
    from core.plugin_loader import load_all_components

    load_all_components(_PLUGINS)


def _analyze(c_env, src: str, *, enabled: list[str] | None = None) -> tuple[AnalysisTraversal, list]:
    """解析 → normalize（生产口径）→ analyze；返回 (traversal, LAB 诊断)。"""
    _ensure_components()
    ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
    assert ast is not None, f"语法层应宽进接受：{src!r}"
    at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
    if enabled is not None:
        at._checks_enabled = list(enabled)
    at.analyze(normalize_ast(ast))
    return at, [d for d in at.diagnostics if str(d.code) in LAB_IDS]


class TestPositiveSamples:
    """判据 1/3：合法形态（含 switch 内 case/default 与 Duff 形态）⇒ 全规则启用下 0 报。"""

    @pytest.mark.parametrize("case", list(POSITIVE))
    def test_legal_form_not_reported(self, c_env, case):
        _, diags = _analyze(c_env, POSITIVE[case], enabled=list(LAB_IDS))
        assert diags == [], (case, diags)

    def test_postpass_is_registered_and_runs(self, c_env):
        """形态证据：labels postpass 出现在 `postpass_trace`（组件被装载并执行）。"""
        at, _ = _analyze(c_env, "void f(void){ lab: ; }\n")
        names = [t["name"] for t in at.postpass_trace]
        assert "rules/_label_check.py:run_label_checks" in names, names


class TestNegativeSamples:
    """判据 2：非法形态 ⇒ 报对应码 + warning + 位置可查 + 重复按"每处一条"。"""

    @pytest.mark.parametrize("case", list(NEGATIVE))
    def test_violation_reported(self, c_env, case):
        src, code, count = NEGATIVE[case]
        at, diags = _analyze(c_env, src, enabled=list(LAB_IDS))
        codes = [d.code for d in diags]
        assert codes == [code] * count, f"{case}: 期望 {code}×{count}，实得 {codes}"
        for d in diags:
            assert d.level == "warning", (case, d.level)
            assert d.node is not None and getattr(d.node, "_pos_line", None) is not None
        errors = [d for d in at.diagnostics if d.level == "error"]
        assert errors == [], (case, errors)

    def test_duplicate_label_position(self, c_env):
        """位置：挂在**第二处**重复 label 的节点上（`_pos_line` = 2）。"""
        src = "void f(void){\n lab: ;\n lab: ;\n}\n"
        _, diags = _analyze(c_env, src, enabled=list(LAB_IDS))
        assert [d.code for d in diags] == ["LAB001"], diags
        assert getattr(diags[0].node, "_pos_line", None) == 3, diags[0].node

    def test_undefined_goto_position(self, c_env):
        """位置：挂在 `goto` 节点上（第二行的 goto）。"""
        src = "void f(void){\n goto nope;\n}\n"
        _, diags = _analyze(c_env, src, enabled=list(LAB_IDS))
        assert [d.code for d in diags] == ["LAB002"], diags
        assert getattr(diags[0].node, "_pos_line", None) == 2, diags[0].node

    def test_case_outside_switch_position(self, c_env):
        src = "void f(void){\n case 1: ;\n}\n"
        _, diags = _analyze(c_env, src, enabled=list(LAB_IDS))
        assert [d.code for d in diags] == ["LAB003"], diags
        assert getattr(diags[0].node, "_pos_line", None) == 2, diags[0].node


class TestDefaultSwitch:
    """三条均 A 档原文 ⇒ `default = true`（Lead 拍板）；severity 统一 warning。"""

    def test_rule_defaults(self):
        table = {
            str(r["id"]): (str(r["kind"]), str(r["severity"]), bool(r.get("default", True)))
            for r in get_check_rules(plugins_dir=_PLUGINS)
            if str(r["id"]) in LAB_IDS
        }
        assert table == {
            "LAB001": ("label", "warning", True),
            "LAB002": ("goto", "warning", True),
            "LAB003": ("switch_label", "warning", True),
        }, table

    def test_default_pass_reports_a_tier(self, c_env):
        for src, code in (
            ("void f(void){ lab: ; lab: ; }\n", "LAB001"),
            ("void f(void){ goto nope; }\n", "LAB002"),
            ("void f(void){ case 1: ; }\n", "LAB003"),
        ):
            _, diags = _analyze(c_env, src)  # 默认档（不注入启用集）
            assert [d.code for d in diags] == [code], (src, [str(d) for d in diags])


class TestLabelProduct:
    """拍板 ⑤：报告同时写 `context.extra["c_labels"]`（观测产物）。"""

    def test_product_shape(self, c_env):
        at, _ = _analyze(c_env, "void f(void){ goto done;\n done: ; done: ; }\n", enabled=list(LAB_IDS))
        product = at.context.extra.get("c_labels")
        assert isinstance(product, dict), at.context.extra.keys()
        funcs = product["functions"]
        assert funcs and funcs[0]["name"] == "f", funcs
        assert funcs[0]["labels"] == ["done"] and funcs[0]["gotos"] == ["done"], funcs
        assert [v["code"] for v in product["violations"]] == ["LAB001"], product["violations"]


class TestCorpusFalsePositives:
    """判据 3（硬要求）：真实语料零误报——含 `ring_buffer.c` 的 `done:`/`goto done;` 与 case/default。"""

    def _corpus(self) -> list[Path]:
        files: list[Path] = []
        for base in CORPUS_DIRS:
            p = Path(base)
            if p.is_dir():
                files.extend(sorted(f for f in p.rglob("*") if f.suffix in (".c", ".h")))
        return files

    def test_corpus_zero_false_positives(self, c_env):
        _ensure_components()
        files = self._corpus()
        assert files, "语料清单为空——判据失效"
        for enabled in (None, list(LAB_IDS)):
            for path in files:
                src = path.read_text(encoding="utf-8")
                ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
                if ast is None:  # 既有语料里本就有 lint 拒的样本，与本节无关
                    continue
                at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
                if enabled is not None:
                    at._checks_enabled = list(enabled)
                at.analyze(normalize_ast(ast))
                hits = [d for d in at.diagnostics if str(d.code) in LAB_IDS]
                assert hits == [], (str(path), enabled is not None, [str(d) for d in hits])

    def test_ring_buffer_mixed_labels_and_switch(self, c_env):
        """硬要求取证：同文件既有 `done:`（LabelStmt）又有 `default:`（DefaultLabel）⇒ 0 报。"""
        from core.define import iter_nodes

        _ensure_components()
        path = Path("tests/languages/c/samples/ring_buffer.c")
        src = path.read_text(encoding="utf-8")
        ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
        assert ast is not None
        norm = normalize_ast(ast)
        counts = {
            name: sum(1 for x in iter_nodes(norm) if x.node_name == name)
            for name in ("FuncDef", "LabelStmt", "GotoStmt", "CaseLabel", "DefaultLabel")
        }
        assert counts == {
            "FuncDef": 9,
            "LabelStmt": 1,
            "GotoStmt": 1,
            "CaseLabel": 2,
            "DefaultLabel": 1,
        }, counts
        at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
        at._checks_enabled = list(LAB_IDS)
        at.analyze(norm)
        assert [d for d in at.diagnostics if str(d.code) in LAB_IDS] == []
        product = at.context.extra["c_labels"]
        entry = next(f for f in product["functions"] if f["name"] == "ring_find")
        assert entry["labels"] == ["done"] and entry["gotos"] == ["done"], entry
        assert all(f["outside_switch"] == 0 for f in product["functions"]), product["functions"]
