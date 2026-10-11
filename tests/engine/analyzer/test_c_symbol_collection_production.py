"""tests/engine/analyzer/test_c_symbol_collection_production.py — C 符号收集的**生产口径**判据。

⚠ **测试必须走生产口径（`normalize_ast` 之后），否则掩盖生产缺陷**（本文件存在的直接原因）：
生产管线的 analyze 输入是 normalize 后的 AST（`transform/normalizer.py`），而 normalize 会
把 token 叶子抽成**字符串属性值**（`keyword.typedef` → `StorageClass.base = "typedef"`）并消除
`optional/repeat/seq` 包装。`tests/languages/c/test_c_symbol_collection.py` 走的是**直接 parse**
（未 normalize）路径，于是"`_subtree_has` 只按节点名判"这一缺陷在生产路径下把 typedef 全收成
`variable` 而**无人发现**（P4 的 raw 校验因此在目标输入上误报 `E002`）。

本文件同时给出两形态的**等价判据**（同一输入 raw/normalize 两次收集，kind 必须逐条一致）
与**安全反例**（字符串字面量 / 注释 / 相似标识符不得被当成 typedef 标记）。
"""

import os

import pytest

from analyzer.traversal import AnalysisTraversal
from core.define import marker_matches
from grammar.c.plugins.semantics import _api
from transform.normalizer import normalize_ast

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")

# 生产口径必须判对的输入（raw / normalize 两形态 kind 必须一致）
CASES: dict[str, str] = {
    "typedef 声明": "typedef int myint;\n",
    "static 声明": "static int z;\n",
    "普通声明": "int plain = 1;\n",
    "struct 标签": "struct point { int x; };\n",
    "enum 标签与常量": "enum color { RED, GREEN };\n",
    "函数定义与参数": "void fn(int p) { int local; }\n",
    "函数声明": "void decl(void);\n",
    "多声明符一行": "typedef int a, b;\n",
    # ── 安全反例：不得被当成 typedef 标记 ──
    "字符串字面量恰为 typedef": 'char *s = "typedef";\n',
    "字符串字面量恰为 int": 'char *s = "int";\n',
    "行尾块注释含 typedef": "int guarded; /* typedef */\n",
    "行注释含 typedef": "int guarded; // typedef\n",
    "独立块注释含 typedef": "/* typedef */\nint guarded;\n",
    "相似标识符": "int typedefx;\n",
}


@pytest.fixture(scope="module")
def c_env():
    """C 包夹具（模块级构造；语言安装态由 conftest 收尾还原）。"""
    from core.config_registry import ConfigRegistry
    from core.define import GrammarRulesRegister
    from lexer import Lexer
    from parser import setup_grammar
    from parser.parser_core import Parser
    from parser.rule_selector import RuleSelector

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
    return {"rules": rules, "parser": parser, "lexer": lexer}


def _records(c_env, src: str, *, production: bool) -> list[dict]:
    """`production=True` 走生产口径（normalize 后）；False 为直接 parse 对照形态。

    ⚠ `normalize_ast` **就地改树**（引擎实现），故两形态必须各 parse 一次。
    """
    from core.plugin_loader import load_all_components

    load_all_components(plugins_dir=_PLUGINS)
    ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
    assert ast is not None, f"解析失败：{src!r}"
    if production:
        ast = normalize_ast(ast)
    at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
    at.analyze(ast)
    return _api.product_from(at)["records"]


def _kinds(records: list[dict], name: str) -> list[str]:
    return [r["kind"] for r in records if r["name"] == name]


class TestProductionForm:
    """生产口径（normalize 后）逐条判据。"""

    def test_typedef_is_collected_as_typedef(self, c_env):
        """核心缺陷判据：normalize 后 `typedef int myint;` 必须收成 `typedef`（曾恒为 variable）。"""
        records = _records(c_env, "typedef int myint;\n", production=True)
        assert _kinds(records, "myint") == [_api.KIND_TYPEDEF], records

    def test_non_typedef_declarations_stay_variable(self, c_env):
        """安全面：普通/静态声明不得因为"值扫描"被误判成 typedef。"""
        for src, name in (("int z;\n", "z"), ("static int z;\n", "z"), ("int z = 1;\n", "z")):
            records = _records(c_env, src, production=True)
            assert _kinds(records, name) == [_api.KIND_VARIABLE], (src, records)

    @pytest.mark.parametrize("case", list(CASES))
    def test_raw_and_production_forms_agree(self, c_env, case):
        """两形态等价：同一输入的 kinds/scope 必须逐条一致（缺陷 = 只在此判据下暴露）。"""
        src = CASES[case]
        raw = [
            (r["name"], r["kind"], r["scope"])
            for r in _records(c_env, src, production=False)
        ]
        prod = [
            (r["name"], r["kind"], r["scope"])
            for r in _records(c_env, src, production=True)
        ]
        assert raw == prod, f"{case}: raw={raw} prod={prod}"

    def test_string_literal_typedef_is_not_a_marker(self, c_env):
        """`char *s = "typedef";` 的 `s` 必须是 variable（字面量保留引号，不等于裸短名）。"""
        records = _records(c_env, 'char *s = "typedef";\n', production=True)
        assert _kinds(records, "s") == [_api.KIND_VARIABLE], records

    def test_comment_typedef_is_not_a_marker(self, c_env):
        """注释里的 `typedef` 不得命中（注释文本不在声明子树内）。"""
        for src in ("int guarded; /* typedef */\n", "int guarded; // typedef\n"):
            records = _records(c_env, src, production=True)
            assert _kinds(records, "guarded") == [_api.KIND_VARIABLE], (src, records)

    def test_kind_coverage_in_production_form(self, c_env):
        """kind 覆盖面在生产口径下齐备：tag / enumerator / function / variable。"""
        src = (
            "typedef int myint;\n"
            "struct point { int x; };\n"
            "enum color { RED };\n"
            "void fn(int p) { int local; }\n"
        )
        records = _records(c_env, src, production=True)
        kinds = {r["name"]: r["kind"] for r in records}
        assert kinds["myint"] == _api.KIND_TYPEDEF, kinds
        assert kinds["point"] == _api.KIND_TAG, kinds
        assert kinds["RED"] == _api.KIND_ENUMERATOR, kinds
        assert kinds["fn"] == _api.KIND_FUNCTION, kinds
        assert kinds["p"] == _api.KIND_VARIABLE and kinds["local"] == _api.KIND_VARIABLE, kinds


class TestMarkerForms:
    """跨形态标记判定（**引擎通用面** `core.define.marker_matches` 的 C 生产口径用法）。

    说明：判定实现已上移到 `core/define.py`（服务所有语言包），故这里直接调**公开面**；
    引擎侧语义与安全反例另有 `tests/engine/core/test_marker_matches.py`——本类只验 C 包
    声明的 marker（`keyword.typedef` / `FuncSuffix`）与槽位形式在**真实 AST** 上的表现。
    """

    def _normalized_decl(self, c_env, src: str):
        from core.define import iter_nodes

        ast = normalize_ast(c_env["parser"].parse(c_env["lexer"].tokenize(src)))
        assert ast is not None
        return next(n for n in iter_nodes(ast) if n.node_name == "Declaration")

    def test_token_prefixed_marker_hits_in_both_forms(self, c_env):
        """`keyword.typedef`：未 normalize 形态（节点名）与 normalize 后（字符串槽）都命中。"""
        from core.define import iter_nodes

        raw_ast = c_env["parser"].parse(c_env["lexer"].tokenize("typedef int myint;\n"))
        assert raw_ast is not None
        raw_decl = next(n for n in iter_nodes(raw_ast) if n.node_name == "Declaration")
        norm_decl = self._normalized_decl(c_env, "typedef int myint;\n")
        assert marker_matches(raw_decl, "keyword.typedef") is True
        assert marker_matches(norm_decl, "keyword.typedef") is True

    def test_syntax_node_marker_is_node_name_only(self, c_env):
        """非 token 前缀的 marker（`FuncSuffix`）仍只认节点名：不给"值扫描"开口子。"""
        decl = self._normalized_decl(c_env, "typedef int myint;\n")
        # 子树里存在字符串值 "typedef"（token 槽），但 marker 不是 token 前缀 ⇒ 不命中
        assert marker_matches(decl, "typedef") is False
        assert marker_matches(decl, "keyword.typedef") is True

    def test_explicit_slot_marker_form(self, c_env):
        """钉槽位形式：`载体.属性=值` 与 dict 两种写法都只认该槽位。"""
        decl = self._normalized_decl(c_env, "typedef int myint;\n")
        assert marker_matches(decl, "StorageClass.base=typedef") is True
        assert marker_matches(decl, "StorageClass.base=int") is False
        assert marker_matches(decl, {"node": "StorageClass", "attr": "base", "value": "typedef"}) is True
        assert marker_matches(decl, {"node": "SimpleType", "attr": "base", "value": "typedef"}) is False
