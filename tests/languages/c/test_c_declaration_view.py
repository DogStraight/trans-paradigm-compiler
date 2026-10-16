"""tests/languages/c/test_c_declaration_view.py — 符号「声明位置派生视图」（N1+N2）判据。

被测（task-47）：
· N1 `_api.declaration_view(analyzer)` —— 逐条给 `decl_scope` / `is_file_decl` / `is_param`
  （FuncDef 位 ⇒ **父作用域**；ParamDecl 位 ⇒ `"param"`；其余沿用分析作用域）；
· N2 `_api.decl_position(node, scope)` 的三元组写进 `Symbol.attrs`（**不进 P1 产物**）。

判据（task-47 1/2/3/4）：
  1. 视图语义：`void proto(int px); void defn(int arg){ int local; } static void stat_def(void){}` ⇒
     `proto`/`defn`/`stat_def` 的文件域声明位、`px`/`arg` 的参数位、`local` 的块位；
  2. **产物零变化（硬要求）**：记录仍是**恰好 7 字段**且取值冻结（本文件冻结快照）；
     改前/改后的逐字节对照由 `_drafts/probe_n1n2_view.py --compare`（11 源 76 记录全 IDENTICAL）给证据；
  3. `test_c_symbol_collection.py` **一个字不改**（它是"零契约面风险"的证据面）；
  4. 两个 S2 场景（**缺陷态变红**见 `_drafts/task47_defect.py`）：
     ① `void f(void); static void f(void){}` ⇒ 两条声明的 `decl_scope` 都是文件域（否则漏报）；
     ② `static int x; void f(int x);` ⇒ 形参不进文件域声明集（否则误报）。
"""

import json
import os

import pytest

from analyzer.traversal import AnalysisTraversal
from core.config_registry import ConfigRegistry
from core.define import GrammarRulesRegister
from grammar.c.plugins.semantics import _api
from lexer import Lexer
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from transform.normalizer import normalize_ast

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")

#: 判据 1 的输入（原型 / 定义 / 静态定义 / 形参 / 块局部 一网打尽）
CASE = (
    "void proto(int px);\nvoid defn(int arg) {\n    int local;\n}\n"
    "static void stat_def(void) {}\n"
)

#: 判据 2 的冻结快照（`product_from(at)["records"]`，**改前采集**；形状 = 7 字段）
FROZEN_SRC = "typedef int myint;\nstatic int x;\nvoid f(int arg) {\n    int local;\n}\n"
FROZEN_RECORDS = [
    {"decl_line": 1, "decl_order": 0, "kind": "typedef", "name": "myint", "phase": "analyze",
     "scope": "<global>", "scope_kind": "global"},
    {"decl_line": 2, "decl_order": 1, "kind": "variable", "name": "x", "phase": "analyze",
     "scope": "<global>", "scope_kind": "global"},
    {"decl_line": 3, "decl_order": 2, "kind": "function", "name": "f", "phase": "analyze",
     "scope": "<global>/FuncDef", "scope_kind": "function"},
    {"decl_line": 3, "decl_order": 3, "kind": "variable", "name": "arg", "phase": "analyze",
     "scope": "<global>/FuncDef", "scope_kind": "function"},
    {"decl_line": 4, "decl_order": 4, "kind": "variable", "name": "local", "phase": "analyze",
     "scope": "<global>/FuncDef/CompoundStmt", "scope_kind": "block"},
]

#: P1 公开产物的记录字段（契约面；**本任务不得改**）
PRODUCT_FIELDS = {"name", "kind", "scope", "scope_kind", "decl_order", "decl_line", "phase"}


@pytest.fixture(scope="module")
def c_env(config_loaded):
    """C 包（含增量组件与语义基座）；结束恢复 verilog。"""
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


def _analyze(c_env, src: str) -> AnalysisTraversal:
    ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
    assert ast is not None, f"语法层应接受：{src!r}"
    at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
    at.analyze(normalize_ast(ast))
    return at


def _view(c_env, src: str) -> dict[str, dict]:
    return {row["name"]: row for row in _api.declaration_view(_analyze(c_env, src))}


class TestViewSemantics:
    """判据 1：`decl_scope` / `is_file_decl` / `is_param` 的语义。"""

    def test_file_scope_functions_and_params_and_block(self, c_env):
        view = _view(c_env, CASE)
        # 函数**声明**：本来就在文件域
        assert view["proto"]["decl_scope"] == "<global>"
        assert view["proto"]["is_file_decl"] is True and view["proto"]["is_param"] is False
        # 函数**定义**：分析作用域是 `<global>/FuncDef`，但声明位置 = 父（文件）作用域
        assert view["defn"]["scope"] == "<global>/FuncDef"
        assert view["defn"]["decl_scope"] == "<global>"
        assert view["defn"]["is_file_decl"] is True
        # static 定义同理
        assert view["stat_def"]["decl_scope"] == "<global>"
        assert view["stat_def"]["is_file_decl"] is True
        # 形参（原型位与定义位）都不是文件域声明
        assert view["px"]["decl_scope"] == "param" and view["px"]["is_param"] is True
        assert view["px"]["is_file_decl"] is False
        assert view["px"]["scope"] == "<global>"  # 分析作用域仍是文件域（偏差①，未修）
        assert view["arg"]["decl_scope"] == "param" and view["arg"]["is_file_decl"] is False
        # 块局部
        assert view["local"]["decl_scope"] == "<global>/FuncDef/CompoundStmt"
        assert view["local"]["is_file_decl"] is False

    def test_view_fields_and_order(self, c_env):
        rows = _api.declaration_view(_analyze(c_env, CASE))
        assert [r["name"] for r in rows] == ["proto", "px", "defn", "arg", "local", "stat_def"]
        for row in rows:
            assert set(row) == {
                "name", "kind", "decl_scope", "is_file_decl", "is_param",
                "scope", "scope_kind", "decl_line", "decl_order", "phase",
            }, row

    def test_n2_attrs_carry_position_triple(self, c_env):
        """N2：三元组进 `Symbol.attrs`（供检查组件按符号读取，不进产物）。"""
        at = _analyze(c_env, CASE)
        by_name = {s.name: (s.attrs or {}) for s in at.all_symbols}
        assert by_name["defn"]["decl_scope"] == "<global>" and by_name["defn"]["is_file_decl"] is True
        assert by_name["px"]["is_param"] is True and by_name["px"]["decl_scope"] == "param"
        assert by_name["local"]["is_file_decl"] is False


class TestProductContractUnchanged:
    """判据 2（硬要求）：P1 公开产物形状与取值零变化。"""

    def test_records_shape_is_exactly_seven_fields(self, c_env):
        records = _api.product_from(_analyze(c_env, FROZEN_SRC))["records"]
        for rec in records:
            assert set(rec) == PRODUCT_FIELDS, rec
            assert "decl_scope" not in rec and "is_param" not in rec and "is_file_decl" not in rec

    def test_records_frozen_snapshot(self, c_env):
        records = _api.product_from(_analyze(c_env, FROZEN_SRC))["records"]
        assert json.dumps(records, ensure_ascii=False, sort_keys=True) == json.dumps(
            FROZEN_RECORDS, ensure_ascii=False, sort_keys=True
        )


class TestS2ScenariosUseView:
    """判据 4 的场景（缺陷态会变红）：只用视图推导"文件域声明集"。"""

    @staticmethod
    def _file_decls(c_env, src: str) -> list[tuple[str, str, str]]:
        return [
            (r["name"], r["kind"], r["decl_scope"])
            for r in _api.declaration_view(_analyze(c_env, src))
            if r["is_file_decl"] and r["kind"] in ("variable", "function")
        ]

    def test_definition_and_declaration_share_decl_scope(self, c_env):
        """缺陷①反例：`void f(void); static void f(void){}` ⇒ 两条声明都判为文件域（否则链接性判定漏报）。"""
        assert self._file_decls(c_env, "void f(void);\nstatic void f(void){}\n") == [
            ("f", "function", "<global>"),
            ("f", "function", "<global>"),
        ]

    def test_param_excluded_from_file_scope(self, c_env):
        """缺陷②反例：`static int x; void f(int x);` ⇒ 形参不进文件域声明集（否则误报）。"""
        assert self._file_decls(c_env, "static int x;\nvoid f(int x);\n") == [
            ("x", "variable", "<global>"),
            ("f", "function", "<global>"),
        ]
