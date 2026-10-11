"""tests/engine/analyzer/test_p4_raw_validate.py — 通用 raw 校验原语 + P4 可达性（task-31 第二步）。

被测：
· `analyzer/primitives/_raw_validate.py::validate_raw_statement`（引擎侧、语言无关）；
· `analyzer/raw_contract.py` 的内建 analyzer 配置回落 + 查询注册面；
· C 包桥 `grammar/c/plugins/semantics/_raw_bridge.py`（语言包声明 kind 语义）。

判据（**raw 节点用构造的**，节点形态按 task-29 冻结契约 A 的 8 条字段）：
  ① 可达性：raw 节点**确实被校验原语访问**（规则表无该节点也要跑——内建配置回落）；
  ② 不过即报错：查询返回 False ⇒ 每条未通过的名字各报 1 条 error（带 code/level/node）；
  ③ 通过不报：查询返回 True ⇒ 无诊断；
  ④ 多名逐个校验；⑤ `raw_eligible=False` ⇒ 跳过（不是 raw 位点）；
  ⑥ 查询解析不到 ⇒ **报错**（安全网缺失绝不静默）；⑦ C 包注册可见 + 真实符号面判定。
"""

import contextlib
import importlib

from core.define import Node
from analyzer.raw_contract import (
    PRIMITIVE_NAME,
    QUERY_AUTO,
    RAW_STATEMENT_NODE_NAME,
    list_raw_name_queries,
    register_raw_name_query,
    resolve_raw_name_query,
)
from analyzer.traversal import AnalysisTraversal

importlib.import_module("tests._bootstrap")  # 副作用导入（sys.path + UTF-8）


@contextlib.contextmanager
def _isolated_query_registry():
    """临时清空查询注册面（用完原样还原）。

    `auto` 语义 = "恰好一个注册项"；同进程内其它测试（如 C 包注册）会让注册数变化 ⇒
    用 `auto` 的判据必须与顺序无关（否则整套跑时假红）。只在本文件内隔离，
    退出即还原，不影响其它测试与生产注册。
    """
    from analyzer.raw_contract import _QUERIES

    saved = dict(_QUERIES)
    _QUERIES.clear()
    try:
        yield
    finally:
        _QUERIES.clear()
        _QUERIES.update(saved)


def _raw_node(**fields) -> Node:
    """构造契约形态的 raw 节点（8 条字段；缺省只填判定必需的几条）。无子节点（契约 A3）。"""
    node = Node(RAW_STATEMENT_NODE_NAME)
    node.add_attr("raw_names", fields.get("names", ["t"]))
    node.add_attr("raw_line", fields.get("line", 3))
    node.add_attr("raw_column", fields.get("column", 15))
    node.add_attr("raw_order", fields.get("order", 1))
    if "eligible" in fields:
        node.add_attr("raw_eligible", fields["eligible"])
    node.add_attr("raw_reason", fields.get("reason", "not-converged"))
    node.add_attr("_verbatim_text", fields.get("verbatim", "(t)y;"))
    node.add_attr("_tok_span", fields.get("span", (5, 11)))
    return node


def _tree(raw: Node) -> Node:
    """最小 AST：TranslationUnit → CompoundStmt(body=[raw])（遍历必须能走到 raw）。"""
    block = Node("CompoundStmt")
    block.add_attr("body", [raw])
    root = Node("TranslationUnit")
    root.add_attr("sub_node", [block])
    return root


def _run(rules: dict | None, raw: Node):
    at = AnalysisTraversal(rules or {})
    ast = _tree(raw)
    at.analyze(ast)
    return at


class TestReachability:
    """① 可达性：raw 节点必须被校验原语访问（否则 M2 摘诊断后无安全网）。"""

    def test_builtin_config_makes_raw_node_reachable(self):
        """规则表里没有 `RawStatement` ⇒ 内建配置回落，原语仍被跑到（并读到全部字段）。"""
        calls: list[dict] = []
        with _isolated_query_registry():  # `auto` 需恰好一个注册项：与其它测试顺序无关
            register_raw_name_query(
                "reach_probe", lambda a, c, n, site: calls.append(site) or True
            )
            raw = _raw_node(names=["t"], line=3, column=15, order=1)
            at = _run({}, raw)  # 空规则表：只能靠内建回落
        assert len(calls) == 1, f"raw 校验原语未被访问（calls={calls}）"
        site = calls[0]
        assert site["name"] == "t"
        assert (site["line"], site["column"], site["order"]) == (3, 15, 1)
        assert site["scope"] == "<global>", site
        assert at.diagnostics == []

    def test_explicit_rule_config_wins_over_builtin(self):
        """语言包在规则表里声明了 `RawStatement` 的 analyzer 段 ⇒ 用自己的（含自定义码）。"""
        from core.define import GrammarRule

        calls: list[str] = []
        register_raw_name_query("explicit_probe", lambda a, c, n, site: calls.append(site["name"]) or True)
        rules = {
            RAW_STATEMENT_NODE_NAME: GrammarRule(
                RAW_STATEMENT_NODE_NAME,
                analyzer={
                    PRIMITIVE_NAME: {
                        "query": "explicit_probe",
                        "code": "E777",
                        "names_attr": "raw_names",
                    }
                },
            )
        }
        try:
            at = _run(rules, _raw_node(names=["myint"]))
            assert calls == ["myint"], calls
            assert at.diagnostics == []
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("explicit_probe", None)


class TestValidationOutcome:
    """②③④⑤⑥ 校验结论：不过即报错、通过不报、多名逐个、eligible 闸门、查询缺失。"""

    def _rules_with(self, query: str, **extra) -> dict:
        from core.define import GrammarRule

        cfg = {"query": query, **extra}
        return {
            RAW_STATEMENT_NODE_NAME: GrammarRule(
                RAW_STATEMENT_NODE_NAME, analyzer={PRIMITIVE_NAME: cfg}
            )
        }

    def test_failing_name_reports_error_never_silent(self):
        register_raw_name_query("always_false", lambda a, c, n, site: False)
        try:
            raw = _raw_node(names=["t"])
            at = _run(self._rules_with("always_false"), raw)
            assert len(at.diagnostics) == 1, at.diagnostics
            d = at.diagnostics[0]
            assert d.level == "error" and d.code == "E002"
            assert "'t'" in d.message, d.message
            assert d.node is raw, "诊断应挂在 raw 节点上（定位用）"
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("always_false", None)

    def test_passing_name_reports_nothing(self):
        register_raw_name_query("always_true", lambda a, c, n, site: True)
        try:
            at = _run(self._rules_with("always_true"), _raw_node(names=["t"]))
            assert at.diagnostics == []
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("always_true", None)

    def test_validate_each_name_individually(self):
        register_raw_name_query("only_t_ok", lambda a, c, n, site: site["name"] == "t")
        try:
            at = _run(self._rules_with("only_t_ok"), _raw_node(names=["t", "u"]))
            assert [d.message for d in at.diagnostics] == [
                "raw 语句中的名称不是类型名: 'u'"
            ], at.diagnostics
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("only_t_ok", None)

    def test_ineligible_site_is_skipped(self):
        """`raw_eligible=False` ⇒ 该位点本就不是 raw 位点（契约 A8），不校验也不报错。"""
        register_raw_name_query("always_false2", lambda a, c, n, site: False)
        try:
            at = _run(self._rules_with("always_false2"), _raw_node(names=["t"], eligible=False))
            assert at.diagnostics == []
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("always_false2", None)

    def test_unregistered_query_reports_error(self):
        """查询解析不到 ⇒ 报错（安全网缺失不能静默）。"""
        at = _run(self._rules_with("no_such_query"), _raw_node(names=["t"]))
        assert len(at.diagnostics) == 1, at.diagnostics
        d = at.diagnostics[0]
        assert d.level == "error" and "未" in d.message, d.message

    def test_missing_names_is_noop(self):
        raw = Node(RAW_STATEMENT_NODE_NAME)
        raw.add_attr("raw_line", 1)
        at = _run(self._rules_with("no_such_query"), raw)
        assert at.diagnostics == []

    def test_unknown_position_sentinels_are_normalized(self):
        """parser 侧的未知哨兵（`raw_order = -1` / 位置 0）不能当数比：归 None 后回落行判据。

        照数比会让 `-1 < decl_order` 恒不成立 ⇒ 合法 raw 位点被全部误报。
        """
        calls: list[dict] = []
        register_raw_name_query("probe_site", lambda a, c, n, site: calls.append(site) or True)
        try:
            at = _run(
                self._rules_with("probe_site"),
                _raw_node(names=["t"], order=-1, line=5, column=3),
            )
            assert at.diagnostics == []
            assert calls and calls[0]["order"] is None, calls
            assert (calls[0]["line"], calls[0]["column"]) == (5, 3), calls
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("probe_site", None)

    def test_no_usable_position_reports_error(self):
        """位置信息全不可用 ⇒ 无法证明"声明在前" ⇒ 报错（不静默放过）。"""
        register_raw_name_query("always_true3", lambda a, c, n, site: True)
        try:
            at = _run(
                self._rules_with("always_true3"),
                _raw_node(names=["t"], order=-1, line=0, column=0),
            )
            assert len(at.diagnostics) == 1, at.diagnostics
            assert "位置" in at.diagnostics[0].message, at.diagnostics[0].message
        finally:
            from analyzer.raw_contract import _QUERIES

            _QUERIES.pop("always_true3", None)


class TestCQueryRegistration:
    """⑦ C 包桥：注册可见 + 真实符号面判定（raw 消费路径的判定体）。"""

    def test_c_query_registered_after_component_load(self):
        from core.config_registry import ConfigRegistry

        ConfigRegistry.load_language("grammar/c", plugins_dir="grammar/c/plugins")
        from core.plugin_loader import load_all_components

        load_all_components(plugins_dir="grammar/c/plugins")
        assert "c_type_name" in list_raw_name_queries(), list_raw_name_queries()
        query, reason = resolve_raw_name_query(QUERY_AUTO)
        assert query is not None, reason

    def test_c_bridge_uses_incremental_symbols(self):
        """桥接查询在遍历期用 `analyzer.all_symbols`（产物未物化）⇒ 声明序/遮蔽语义成立。"""
        from core.config_registry import ConfigRegistry
        from core.define import GrammarRulesRegister
        from lexer import Lexer
        from parser import setup_grammar
        from parser.parser_core import Parser
        from parser.rule_selector import RuleSelector
        from grammar.c.plugins.semantics import _raw_bridge

        pack, plugins = "grammar/c", "grammar/c/plugins"
        ConfigRegistry.load_language(pack, plugins_dir=plugins)
        rules = setup_grammar(pack, GrammarRulesRegister(), ext_dirs=[plugins])
        stmt = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        parser = Parser(
            rules_dir=pack,
            rules=rules,
            rule_selector=RuleSelector(rules, stmt),
            log_file="",
        )
        lexer = Lexer(rules_dir=pack, ext_dirs=[plugins])

        def analyze(src: str) -> AnalysisTraversal:
            ast = parser.parse(lexer.tokenize(src))
            assert ast is not None, src
            at = AnalysisTraversal(rules, rules_dir=pack)
            at.analyze(ast)
            return at

        node = Node(RAW_STATEMENT_NODE_NAME)
        # P1 代理源（全局 typedef、块内使用）⇒ 类型名
        at_ok = analyze("typedef int t;\nvoid f(void){ x = t; }\n")
        site = {"name": "t", "scope": "<global>/FuncDef/CompoundStmt", "order": 1, "line": 2}
        assert _raw_bridge.query_type_name(at_ok, at_ok.context, node, site) is True
        # P2 代理源（块内 `int t` 遮蔽）⇒ 不是类型名
        at_shadow = analyze("typedef int t;\nvoid f(void){ int t; x = t; }\n")
        shadow = {"name": "t", "scope": "<global>/FuncDef/CompoundStmt", "order": 3, "line": 2}
        assert _raw_bridge.query_type_name(at_shadow, at_shadow.context, node, shadow) is False
