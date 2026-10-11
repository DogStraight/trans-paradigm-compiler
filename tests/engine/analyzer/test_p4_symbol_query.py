"""tests/engine/analyzer/test_p4_symbol_query.py — P4 专用符号查询（task-31 第一步）。

被测：`grammar/c/plugins/semantics/_p4_query.py::is_type_name` —— "祖先作用域 +
最近声明遮蔽 + `(decl_order, line, column)` 顺序 + tag 排除"。

判据 6 组（P1/P2/P3+P11/P10+P12/Q1）+ tag 排除；`records` 由 C 包真实分析产出
（用**可解析的代理源**构造同名同作用域结构：目标形态 `(t)y` 本身今天解析不了，
那正是 P4 要解决的问题 ⇒ 查询单测只取它需要的 records 结构 + 显式 use site）。

另附 shipped `_api.is_typedef` 的两处实测误判（本查询存在的理由）。
"""

import os

import pytest

from analyzer.traversal import AnalysisTraversal
from grammar.c.plugins.semantics import _api, _p4_query
from grammar.c.plugins.semantics._p4_query import UseSite

_RULES = "grammar/c"
_PLUGINS = os.path.join(_RULES, "plugins")

# ── 场景表：(id, 代理源, use site 参数, 期望) ─────────────────────────────
# use site 的 scope/order/line 按"raw 节点会给出的值"填（见各条注释）。
SCENES: dict[str, tuple[str, dict, bool]] = {
    # P1 目标输入：全局 typedef + 块内使用 ⇒ 必须接受
    "P1": (
        "typedef int t;\nvoid f(void){ x = t; }\n",
        {"name": "t", "scope": "<global>/FuncDef/CompoundStmt", "order": 1, "line": 2},
        True,
    ),
    # P2 遮蔽：块内 `int t`（更深作用域）⇒ 必须拒绝（gcc 判非法）
    "P2": (
        "typedef int t;\nvoid f(void){ int t; x = t; }\n",
        {"name": "t", "scope": "<global>/FuncDef/CompoundStmt", "order": 3, "line": 2},
        False,
    ),
    # P3 同作用域重声明：typedef 后同作用域 int ⇒ 最近声明是变量 ⇒ 拒绝
    "P3": (
        "typedef int t;\nint t;\nx = t;\n",
        {"name": "t", "scope": "<global>", "order": 2, "line": 3},
        False,
    ),
    # P11 同作用域重复 typedef（两条都是 typedef）⇒ 接受
    "P11": (
        "typedef int t;\ntypedef int t;\nx = t;\n",
        {"name": "t", "scope": "<global>", "order": 2, "line": 3},
        True,
    ),
    # P10 函数声明参数（无 typedef）：`t` 只有参数记录 ⇒ 拒绝
    "P10": (
        "void f(int t);\nx = t;\n",
        {"name": "t", "scope": "<global>", "order": 2, "line": 2},
        False,
    ),
    # P12 定义参数遮蔽全局 typedef ⇒ 拒绝（C：参数是普通标识符）
    "P12": (
        "typedef int t;\nvoid f(int t){ x = t; }\n",
        {"name": "t", "scope": "<global>/FuncDef/CompoundStmt", "order": 3, "line": 2},
        False,
    ),
    # Q1 同行先使用后声明：use 序在声明之前 ⇒ 拒绝
    "Q1": (
        "void f(void){ x = t; typedef int t; }\n",
        {"name": "t", "scope": "<global>/FuncDef/CompoundStmt", "order": 0, "line": 1},
        False,
    ),
    # tag 排除：标签是另一个命名空间，不成类型名 ⇒ 拒绝
    "TAG": (
        "struct t{};\nx = t;\n",
        {"name": "t", "scope": "<global>", "order": 1, "line": 2},
        False,
    ),
    # tag 排除的反向：同名 typedef 与 tag 并存 ⇒ 标签**不参与竞争**，typedef 仍生效 ⇒ 接受
    "TAG2": (
        "typedef int t;\nstruct t {};\nx = t;\n",
        {"name": "t", "scope": "<global>", "order": 2, "line": 3},
        True,
    ),
}


@pytest.fixture(scope="module")
def c_env():
    """C 包夹具（解析 + analyze；模块级构造，语言安装态由 conftest 收尾还原）。"""
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


def _records(c_env, src: str) -> list[dict]:
    """真实分析产出（analyze 期 records）。组件表是测试级全局态 ⇒ 用前按生产路径补回。"""
    from core.plugin_loader import load_all_components

    load_all_components(plugins_dir=_PLUGINS)
    ast = c_env["parser"].parse(c_env["lexer"].tokenize(src))
    assert ast is not None, f"解析失败：{src!r}"
    at = AnalysisTraversal(c_env["rules"], rules_dir=_RULES)
    at.analyze(ast)
    return _api.product_from(at)["records"]


@pytest.mark.parametrize("scene", list(SCENES))
def test_p4_query_scenes(c_env, scene):
    """6 组判据逐条：P1 接受；P2/P3/P10/P12/Q1/TAG 拒绝。"""
    src, use_kwargs, expected = SCENES[scene]
    records = _records(c_env, src)
    got = _p4_query.is_type_name(UseSite(**use_kwargs), records)
    assert got is expected, f"{scene}: expected {expected}, got {got}（records={records}）"


def test_same_line_without_order_is_undecidable(c_env):
    """Q1 退路：只有行号且同行 ⇒ 不可判 ⇒ 拒绝（默认偏置 not typedef，不误接受）。"""
    records = _records(c_env, SCENES["Q1"][0])
    use = UseSite(name="t", scope="<global>/FuncDef/CompoundStmt", line=1)
    assert _p4_query.is_type_name(use, records) is False


def test_undeclared_name_defaults_to_not_type_name(c_env):
    """未声明标识符 ⇒ 默认偏置 `not typedef`（显式口径）。"""
    records = _records(c_env, "int x;\n")
    assert _p4_query.is_type_name(UseSite(name="nosuch", scope="<global>"), records) is False
    assert _api.DEFAULT_TYPEDEF_BIAS == "not typedef"


def test_nearest_declaration_wins_over_outer_typedef(c_env):
    """"最近声明"选择本身可证伪：P2 与 P12 必须选中**内层**那条（变量/参数）。"""
    p2 = _p4_query.nearest_declaration(
        UseSite(**SCENES["P2"][1]), _records(c_env, SCENES["P2"][0])
    )
    assert (p2 or {}).get("kind") == "variable" and (p2 or {}).get("scope") == (
        "<global>/FuncDef/CompoundStmt"
    ), p2
    p12 = _p4_query.nearest_declaration(
        UseSite(**SCENES["P12"][1]), _records(c_env, SCENES["P12"][0])
    )
    assert (p12 or {}).get("kind") == "variable" and (p12 or {}).get("scope") == (
        "<global>/FuncDef"
    ), p12


def test_tag_record_never_makes_a_type_name(c_env):
    """tag 排除：`struct t{};` 的 tag 记录存在时仍拒绝（另一个命名空间）。"""
    records = _records(c_env, SCENES["TAG"][0])
    assert [r["kind"] for r in records if r["name"] == "t"] == ["tag"], records
    assert _p4_query.is_type_name(UseSite(**SCENES["TAG"][1]), records) is False


def test_shipped_api_misjudges_where_p4_query_is_correct(c_env):
    """本查询存在的理由（实测两处误判，二者不可兼得）：

    · P1（目标输入）用**真实作用域**精确匹配 ⇒ shipped API **误拒**（False）；
    · P2（遮蔽例）用 `scope=None` 只看同名 typedef 记录 ⇒ shipped API **误接受**（True）。
    """
    p1_records = _records(c_env, SCENES["P1"][0])
    p2_records = _records(c_env, SCENES["P2"][0])

    shipped_p1 = _api.is_typedef(
        "t", p1_records, scope="<global>/FuncDef/CompoundStmt"
    )
    shipped_p2 = _api.is_typedef("t", p2_records)
    assert (shipped_p1, shipped_p2) == (False, True), (shipped_p1, shipped_p2)

    p4_p1 = _p4_query.is_type_name(UseSite(**SCENES["P1"][1]), p1_records)
    p4_p2 = _p4_query.is_type_name(UseSite(**SCENES["P2"][1]), p2_records)
    assert (p4_p1, p4_p2) == (True, False), (p4_p1, p4_p2)
