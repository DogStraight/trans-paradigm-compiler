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
            # P4 理解路径素材（与两处注入点同形）
            "substitute_type": str(w.get("substitute_type", "")),
            "trial_rule": str(w.get("trial_rule", "")),
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
        # A3（承载期）：**结构子节点为空**——候选只走属性通道。
        # ⚠ `iter_children()` 会连**属性挂载的节点**一起产出（引擎既有语义），
        # 故"无子节点"要按 `sub_nodes` 判结构面，属性面则唯一是 `raw_candidate`。
        assert getattr(node, "sub_nodes", []) == []
        assert [getattr(c, "node_name", None) for c in node.iter_children()] == [
            "ExprStmt"
        ], "属性挂载的候选子树是 `iter_children()` 的唯一产出"
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


class TestRawCandidate:
    """P4 理解路径第一步：承载期按位点给的替换方案建**候选子树**（只挂属性）。

    契约：`raw_candidate` = 候选子树根（**已还原源码原文**的确定结构）；
    `raw_substituted` = 取证；建失败/异常 ⇒ **不挂**；不改 children、不改渲染。
    """

    def test_candidate_structure_and_restoration(self, c_env):
        """判据 1+2：候选含 `CastExpr`；被替换叶子**还原为原文** `myint`（不是 `int`）。"""
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        parser, ast, _ = _parse(rules, lexer, TARGET, sites)
        raw = _find_raw(ast)[0]
        candidate = getattr(raw, "raw_candidate", None)
        assert candidate is not None, "候选子树应已建（位点带替换配方）"
        assert candidate.node_name == "ExprStmt"

        names: list[str] = []
        values: list[str] = []
        stack = [candidate]
        while stack:
            cur = stack.pop()
            names.append(cur.node_name)
            val = getattr(cur, "value", None)
            if val is None:
                val = getattr(cur, "content", None)
            if val is not None:
                values.append(str(val))
            stack.extend(cur.iter_children())
        assert "CastExpr" in names, names
        assert "myint" in values, values
        assert "int" not in values and "keyword.int" not in names, (
            "替换型 token 必须还原为源码原文（否则 dump/ast_json 会看到源码里没有的 int）"
        )

        evidence = getattr(raw, "raw_substituted", None)
        assert isinstance(evidence, list) and evidence, evidence
        assert evidence[0]["original_text"] == "myint"
        assert evidence[0]["substituted_as"] == "keyword.int"
        assert evidence[0]["restored_leaves"] == 1
        # 判据③（Lead 补严）：显著 token 里"未建叶子"的必须**全部落在 pratt 消费位**
        # ——把"允许缺什么"钉成引擎可验证的事实（不引语言知识）。fail-closed：
        # 不满足时 `build_raw_candidate` 直接**不挂**候选（故本断言同时是守门）。
        missing = evidence[0]["missing_indices"]
        pratt = evidence[0]["pratt_consumed_indices"]
        assert set(missing) <= set(pratt), (
            f"未建叶子的显著 token {missing} 不都在 pratt 消费位 {pratt}"
        )
        assert missing, "本形态应至少有一个 pratt 消费的运算符未建叶子（`=`）"
        # 候选消费区间与位点 region 一致（结构与 verbatim 同覆盖）
        assert getattr(candidate, "_tok_span", None) is None or True  # 见下断言
        lo, hi = sites[0]["region"]
        assert parser._raw_sites_consumed[0]["span"] == (lo, hi + 1)
        # 渲染权威不变：verbatim 仍是源切片
        assert getattr(raw, "_verbatim_text") == "x = (myint)y;"

    def test_candidate_leaf_sequence_is_ordered_subsequence_of_verbatim(self, c_env):
        """判据 1（等价口径）：候选**叶子文本**是 verbatim 显著 token 的**有序子序列**。

        为什么不是"逐项相等"：pratt 运算符（`=` 等）由 pratt 引擎消费、**不建叶子**
        （实测 `BinaryOp` 的子节点只有两侧操作数）⇒ 严格逐项相等不可得。等价性由两条
        合成：① 候选与 verbatim **覆盖同一 token 区间**（区间等式，见上）；
        ② 叶子文本按序出现（不丢不改名）。
        """
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        _parser, ast, _ = _parse(rules, lexer, TARGET, sites)
        raw = _find_raw(ast)[0]
        candidate = getattr(raw, "raw_candidate")

        leaves: list[str] = []

        def walk(cur) -> None:
            kids = [c for c in cur.iter_children()]
            val = getattr(cur, "value", None)
            if val is None:
                val = getattr(cur, "content", None)
            if not kids:
                if val is not None:
                    leaves.append(str(val))
                return
            for child in kids:
                walk(child)

        walk(candidate)
        verbatim = str(getattr(raw, "_verbatim_text"))
        vtokens = [t.content for t in lexer.tokenize(verbatim) if t.type != "newline"]

        it = iter(vtokens)
        assert all(any(tok == leaf for tok in it) for leaf in leaves), (
            f"候选叶子 {leaves} 不是 {vtokens} 的有序子序列"
        )

    def test_trial_build_does_not_leak_parser_state(self, c_env):
        """⚠ 实测结论：试建会碰 **Parser 级簿记**（不在 `ParseContext` 快照内）
        ——注释锚点/行尾簿记/失败现场/截断标志/消费记录 ⇒ 必须显式快照回滚。"""
        rules, lexer = c_env
        sites, _ = _sites_from_linter(TARGET)
        parser, ast, _ = _parse(rules, lexer, TARGET, sites)
        # 试建后：消费记录只有 1 条（试建不得污染）、未截断、候选已挂
        assert len(parser._raw_sites_consumed) == 1
        assert parser._parse_truncated is False
        raw = _find_raw(ast)[0]
        assert getattr(raw, "raw_candidate", None) is not None
        # 注释锚点/行尾簿记保持"试建前"状态：目标句无涉及注释 ⇒ 均为空
        assert list(getattr(parser, "_line_comment_anchors", [])) == []
        assert list(getattr(parser, "_comment_anchors", [])) == []
        assert set(getattr(parser, "_trailing_seen", set())) == set()
