"""Linter 消歧（LookaheadTable）单元测试 — 动态两级消歧契约。

固定 discovery 消歧的当前行为，独立于 lint_err 样本集：
    - 样本集覆盖"最终诊断"（黑盒）
    - 本测试覆盖"消歧决策"（classify 返回的候选规则集）

通过 LinterScanner 暴露的内部 LookaheadTable 直接断言：
    - A 类：关键字触发 → 候选规则
    - B 类：标识符触发 → 按上下文过滤 + 变长前瞻消歧
    - 未识别：候选清空 → 返回 []（discovery 据此报 phase-unrecognized）
    - 非语句起点：无候选 → 返回 None（与 [] 区分）
"""

import pytest
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


@pytest.fixture(scope="module")
def scanner(config_loaded):
    from linter.scanner import LinterScanner

    return LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)


@pytest.fixture(scope="module")
def lookahead(scanner):
    return scanner._discovery._lookahead


def _tokens(scanner, src):
    return scanner.lexer.tokenize(src)


def _classify_at(lookahead, tokens, content):
    """定位 content 的 token，返回其 classify 结果（list | None）。"""
    for i, t in enumerate(tokens):
        if t.content == content:
            return lookahead.classify(tokens, i)
    raise AssertionError(f"token '{content}' not found in token stream")


class TestIdentCandidates:
    """B 类 ident 候选注册到单一全局集合（不按上下文分组）。"""

    def test_ident_candidates_non_empty(self, lookahead):
        assert lookahead.ident_candidates, "B 类 ident 候选应非空"


class TestAClassKeyword:
    """A 类：关键字触发 → 两级消歧收敛到具体规则。"""

    def test_if_keyword_classifies_to_ifblock(self, scanner, lookahead):
        tokens = _tokens(scanner, "module m; if (x) begin end endmodule")
        assert _classify_at(lookahead, tokens, "if") == ["IfBlock"]

    def test_always_classifies_to_alwaysstmt(self, scanner, lookahead):
        tokens = _tokens(scanner, "module m; always @(*) begin end endmodule")
        assert _classify_at(lookahead, tokens, "always") == ["AlwaysStmt"]


class TestBClassIdent:
    """B 类：标识符触发，变长前瞻消歧（不按上下文过滤）。"""

    def test_proc_blocking_assign(self, scanner, lookahead):
        tokens = _tokens(scanner, "module m; always @(*) begin a = 1; end endmodule")
        assert _classify_at(lookahead, tokens, "a") == ["BlockingAssign"]

    def test_proc_nonblocking_assign(self, scanner, lookahead):
        tokens = _tokens(scanner, "module m; always @(*) begin b <= 1; end endmodule")
        assert _classify_at(lookahead, tokens, "b") == ["NonBlockingAssign"]

    def test_proc_subroutine_call(self, scanner, lookahead):
        tokens = _tokens(scanner, "module m; always @(*) begin c(x); end endmodule")
        assert _classify_at(lookahead, tokens, "c") == ["SubroutineCall"]

    def test_module_inst(self, scanner, lookahead):
        tokens = _tokens(scanner, "module m; foo u1 (.a(b)); endmodule")
        assert _classify_at(lookahead, tokens, "foo") == ["ModuleInst"]

    def test_level1_disambiguates_inst(self, scanner, lookahead):
        # 同一 ident：Level 1 前瞻消歧（foo u1( 两 token 预视）定 ModuleInst
        tokens = _tokens(scanner, "module m; foo u1 (.a(b)); endmodule")
        assert _classify_at(lookahead, tokens, "foo") == ["ModuleInst"]

    def test_param_inst_cross_line(self, scanner, lookahead):
        # 跨行参数化实例化（模块名/参数/实例名分多行，SERV 风格）：
        # foo\n  #(.P(p))\nbar\n  (...)\n → 仍分类为 ModuleInst
        tokens = _tokens(
            scanner,
            "module m; foo\n  #(.P(p))\nbar\n  (.a(b)); endmodule",
        )
        assert _classify_at(lookahead, tokens, "foo") == ["ModuleInst"]


class TestUnrecognized:
    """未识别语法（候选清空）→ 返回 []（discovery 报 phase-unrecognized）。"""

    def test_typo_keyword(self, scanner, lookahead):
        # e07: alwayss 拼错 → 无候选匹配 → []
        tokens = _tokens(scanner, "module m; alwayss @(*) begin end endmodule")
        assert _classify_at(lookahead, tokens, "alwayss") == []

    def test_if_missing_paren(self, scanner, lookahead):
        # e09: if 缺括号 → Level 1 前瞻 paths 失败 → []
        tokens = _tokens(scanner, "module m; always @(*) begin if a begin end end endmodule")
        assert _classify_at(lookahead, tokens, "if") == []


class TestNonStatement:
    """非语句起点 → 返回 None（与 [] 的"未识别"区分）。"""

    def test_semicolon_is_nullstmt(self, scanner, lookahead):
        # 分号是 NullStmt（空语句）起点 → 返回 ['NullStmt']，不是 None
        tokens = _tokens(scanner, "module m; endmodule")
        for i, t in enumerate(tokens):
            if t.type == "symbol.base.semicolon":
                assert lookahead.classify(tokens, i) == ["NullStmt"]
                return
        raise AssertionError("no semicolon token found")

    def test_operator_is_not_statement_start(self, scanner, lookahead):
        # 运算符（+）不是语句起点：无候选 → None
        tokens = _tokens(scanner, "a + b")
        for i, t in enumerate(tokens):
            if t.type == "symbol.base.add":
                assert lookahead.classify(tokens, i) is None
                return
        raise AssertionError("no '+' token found")


class TestTryParseProbe:
    """Level 2 试解析（_try_parse）的 probe 模式：截断 limit 不因 EOF 误判失败。

    固化修复：_try_parse 的 limit 是人为截断的（句子边界+1），
    语句区间在 EOF 处耗尽是正常截断而非残缺——probe 使其不报 EOF 错误，
    否则合法 for 被误判为未识别（曾引发 normal 样本误报回归）。
    """

    def test_try_parse_valid_for_in_truncated_limit(self, scanner, lookahead):
        # 合法 for：截断 limit 下 @Stmt 在 limit 外是正常截断，probe 生效 → 返回
        # [ForLoop] 而非 []（防 for 误报回归）
        tokens = _tokens(scanner, "for (i = 0; i < 8; i = i + 1) a = 1;")
        entries = lookahead.keyword_map.get("keyword.for", [])
        assert entries
        i = next(k for k, t in enumerate(tokens) if t.type == "keyword.for")
        limit = lookahead._find_boundary(tokens, i + 1, len(tokens))
        result = lookahead._try_parse(
            tokens, i, entries, min(limit + 1, len(tokens))
        )
        assert result == ["ForLoop"]
