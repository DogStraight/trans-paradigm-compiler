"""P3c/M2 raw 承载（parser 侧）：冻结契约 A/B/C 的**单测**。

契约（`linter/linter_architecture.md`「raw 承载」节 + task-29）：
  A. 节点 8 条字段：节点名 `RawStatement`（单一来源 `parser.block_parser.RAW_NODE_NAME`）、
     `_verbatim_text`（渲染权威）、**无子节点**、`raw_names`、`raw_line`/`raw_column`、
     `raw_order`、`_tok_span`、`raw_reason`/`raw_eligible`；
  B. 位点启用：**精确 (line, column)**（**无 fallback**）+ 该 token 是语句元素起点；
  C. 区间等式：`consumed == region`（token 下标，含 trivia）；不满足走既有失败路径。

测试直接驱动 `Parser`（不经管线），位点表按 pipeline 的最小通道（纯 dict）注入。
"""

import pytest

from core.config_registry import ConfigRegistry
from core.define import DEFAULT_RULES_DIR, GrammarRulesRegister
from lexer import Lexer
from parser import Parser, setup_grammar

C_PACK, C_PLUGINS = "grammar/c", "grammar/c/plugins"
TARGET = "typedef int myint;\nvoid f(void) { x = (myint)y; }\n"


@pytest.fixture
def c_env(config_loaded):
    """C 包环境：规则表 + token 流 + Parser（用完切回 verilog）。"""
    del config_loaded
    try:
        ConfigRegistry.load_language(C_PACK, plugins_dir=C_PLUGINS)
        rules = setup_grammar(
            C_PACK, GrammarRulesRegister.get_default(), ext_dirs=[C_PLUGINS]
        )
        lexer = Lexer(rules_dir=C_PACK, ext_dirs=[C_PLUGINS])
        yield rules, lexer
    finally:
        ConfigRegistry.load_language(
            DEFAULT_RULES_DIR, plugins_dir="grammar/verilog/plugins"
        )


def _parse(rules, lexer, source: str, sites: list[dict]):
    from parser.rule_selector import RuleSelector

    stmt_names = [
        n for n, r in rules.items() if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    parser = Parser(
        rules_dir=C_PACK,
        rules=rules,
        rule_selector=RuleSelector(rules, stmt_names),
    )
    parser.raw_sites = sites
    parser.raw_source = source
    tokens = lexer.tokenize(source)
    ast = parser.parse(tokens)
    return parser, ast, tokens


def _sites_from_linter(source: str) -> tuple[list[dict], list[dict]]:
    """按 pipeline 的最小通道取位点（`eligible` 且含 region）。"""
    from linter.scanner import LinterScanner

    scanner = LinterScanner(C_PACK, ext_dirs=[C_PLUGINS])
    scanner.scan(source)
    warns = scanner.internal_warnings()
    sites = [
        {
            "line": int(w["line"]),
            "column": int(w["column"]),
            "region": (int(w["region"][0]), int(w["region"][1])),
            "names": list(w.get("symbol_names") or []),
            "reason": str(w.get("reason", "")),
            "order": int(w.get("pos", -1)),
        }
        for w in warns
        if w.get("eligible") and w.get("region")
    ]
    return sites, warns


def _find_raw(ast):
    found = []
    stack = [ast]
    while stack:
        node = stack.pop()
        if node is None or not hasattr(node, "node_name"):
            continue
        if node.node_name == "RawStatement":
            found.append(node)
        stack.extend(node.iter_children())
    return found


class TestRawNodeContract:
    """契约 A：字段齐备、无子节点、渲染权威文本保真。"""

    def test_contract_fields_and_no_children(self, c_env):
        rules, lexer = c_env
        sites, _warns = _sites_from_linter(TARGET)
        assert len(sites) == 1, "目标句应有 1 个合格位点"
        _parser, ast, _tokens = _parse(rules, lexer, TARGET, sites)

        raw = _find_raw(ast)
        assert len(raw) == 1, "应产出且仅产出一个 RawStatement"
        node = raw[0]
        assert node.node_name == "RawStatement"
        # A3：**无子节点**（否则渲染不遍历子节点、分析遍历子节点 ⇒ 两套真值）
        assert list(node.iter_children()) == []
        # A2：`_verbatim_text` = 渲染权威（源码切片，逐字节保真）
        assert getattr(node, "_verbatim_text") == "x = (myint)y;"
        # A4–A6、A8：契约字段
        assert getattr(node, "raw_names") == ["myint"]
        assert (getattr(node, "raw_line"), getattr(node, "raw_column")) == (2, 15)
        assert getattr(node, "raw_order") == sites[0]["order"]
        assert getattr(node, "raw_eligible") is True
        assert getattr(node, "raw_reason") == sites[0]["reason"]
        # A7：token 下标区间 = region 半开化
        lo, hi = sites[0]["region"]
        assert getattr(node, "_tok_span") == (lo, hi + 1)

    def test_region_equality_and_no_truncation(self, c_env):
        """契约 C：消费区间与位点 region **逐位相等**；且不再截断。"""
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        lo, hi = sites[0]["region"]
        parser, ast, tokens = _parse(rules, lexer, TARGET, sites)
        assert parser._raw_sites_consumed, "位点应被消费"
        span = parser._raw_sites_consumed[0]["span"]
        assert span == (lo, hi + 1)
        assert tokens[span[0]].content == "x"
        assert tokens[span[1] - 1].type == "symbol.base.semicolon"
        assert parser._parse_truncated is False
        assert _find_raw(ast), "raw 节点应在 AST 里"


class TestSiteEnableConditions:
    """契约 B/C 的反面：不满足即**不消费**（走既有失败路径，不静默）。"""

    def test_no_fallback_on_column_drift(self, c_env):
        """精确 (line, column)：位点列**偏小**一位即不命中（**无同行 fallback**）。

        方向说明：历史 fallback 是"同行内第一个 `token.column >= site.column`"——
        它专门吞掉"位点列比真实 token 列小"的漂移（展开态列漂移的典型方向），
        故回归用例必须往**偏小**方向造漂移，否则测不到该 fallback。
        """
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        drifted = [dict(sites[0], column=sites[0]["column"] - 1)]
        parser, ast, _ = _parse(rules, lexer, TARGET, drifted)
        assert parser._raw_sites_consumed == []
        assert _find_raw(ast) == []
        assert parser._parse_truncated is True  # 既有失败路径（截断），不是静默通过

    def test_no_fallback_on_line_drift(self, c_env):
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        drifted = [dict(sites[0], line=sites[0]["line"] + 1)]
        parser, ast, _ = _parse(rules, lexer, TARGET, drifted)
        assert parser._raw_sites_consumed == [] and _find_raw(ast) == []
        assert parser._parse_truncated is True

    def test_region_lower_bound_must_match_pointer(self, c_env):
        """区间等式前半：region 下界 ≠ 当前位置 ⇒ 不消费。"""
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        lo, hi = sites[0]["region"]
        bad = [dict(sites[0], region=(lo + 1, hi))]
        parser, ast, _ = _parse(rules, lexer, TARGET, bad)
        assert parser._raw_sites_consumed == [] and _find_raw(ast) == []

    def test_region_upper_bound_beyond_eof_ignored(self, c_env):
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        lo, _hi = sites[0]["region"]
        bad = [dict(sites[0], region=(lo, 10**6))]
        parser, ast, _ = _parse(rules, lexer, TARGET, bad)
        assert parser._raw_sites_consumed == [] and _find_raw(ast) == []

    def test_empty_sites_mechanism_off(self, c_env):
        """空位点表 ⇒ 机制关闭（与引入前一致：截断失败）。"""
        rules, lexer = c_env
        parser, ast, _ = _parse(rules, lexer, TARGET, [])
        assert parser._raw_sites_consumed == [] and _find_raw(ast) == []
        assert parser._parse_truncated is True
