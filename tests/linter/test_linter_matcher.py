"""Linter 匹配契约单元测试 — RuleMatcher / StatementChecker / ExpressionChecker。

固定共享匹配器对语句/块/表达式的匹配行为，独立于 lint_err 样本集：
    - @Stmt 对 begin 块 body 静默跳过（合法）
    - @Stmt 对坏 body（endmodule）报 phase-statement（e15 修复行为）
    - @BeginEnd 校验 block_start（非 begin 起点不跳过）
    - StatementChecker / ExpressionChecker 的基本契约
"""

import pytest
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


@pytest.fixture(scope="module")
def scanner(config_loaded):
    from linter.scanner import LinterScanner

    return LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)


def _tokens(scanner, src):
    return scanner.lexer.tokenize(src)


class TestMatcherStatement:
    """RuleMatcher 对语句/块引用的匹配契约。"""

    def test_stmt_call_on_begin_is_silent(self, scanner):
        # @Stmt 对 begin 块 body：合法，静默跳过整个块（不报错）
        tokens = _tokens(scanner, "begin a = 1; end")
        errs = []
        j = scanner._matcher.match(
            tokens, 0, {"type": "call", "name": "Stmt"}, errs, len(tokens), strict=True
        )
        assert errs == []
        assert j > 0

    def test_stmt_call_on_endmodule_reports(self, scanner):
        # @Stmt 对坏 body（endmodule）：报 phase-statement（e15 修复后行为）
        tokens = _tokens(scanner, "endmodule")
        errs = []
        scanner._matcher.match(
            tokens, 0, {"type": "call", "name": "Stmt"}, errs, len(tokens), strict=True
        )
        assert any(e.code == "phase-statement" for e in errs)

    def test_block_call_requires_block_start(self, scanner):
        # @BeginEnd 非 begin 起点（endmodule）：不跳过（视为失败，j==0）
        tokens = _tokens(scanner, "endmodule")
        errs = []
        j = scanner._matcher.match(
            tokens, 0, {"type": "call", "name": "BeginEnd"}, errs, len(tokens), strict=True
        )
        assert j == 0

    def test_block_call_on_begin_skips_block(self, scanner):
        # @BeginEnd 对 begin 起点：校验通过，跳过整个块到 end（无错误、消费到末尾）
        tokens = _tokens(scanner, "begin a = 1; end")
        errs = []
        j = scanner._matcher.match(
            tokens, 0, {"type": "call", "name": "BeginEnd"}, errs, len(tokens), strict=True
        )
        assert errs == []
        assert j == len(tokens)

    def test_assign_missing_semicolon_reports(self, scanner):
        # 完整 scan：assign 缺分号 → phase-statement（快速回归，不依赖样本文件）
        src = "module m;\n    assign a = b\nendmodule\n"
        errs = scanner.scan(src)
        assert any(e.code == "phase-statement" for e in errs)

    def test_valid_assign_no_error(self, scanner):
        src = "module m;\n    assign a = b;\nendmodule\n"
        assert scanner.scan(src) == []

    def test_missing_semicolon_eof_no_newline_reports(self, scanner):
        # 无末尾换行 + 缺分号（缺失 token 处即 EOF）→ phase-statement。
        # 修复：此前 match_rule 在 i>=limit 静默 break → 完全漏检（只有 boundary）。
        src = "module m;\n    assign a = b"  # 无末尾换行，缺分号 + 缺 endmodule
        errs = scanner.scan(src)
        assert any(e.code == "phase-statement" for e in errs)

    def test_bad_always_body_eof_no_newline_reports(self, scanner):
        # 无末尾换行 + always 坏 body（endmodule 紧随 @(*)）→ phase-statement。
        # 修复：此前 e15 去末尾换行后 n=0 完全漏检。
        src = "module m;\n    always @(*) endmodule"
        errs = scanner.scan(src)
        assert any(e.code == "phase-statement" for e in errs)

    def test_valid_assign_eof_no_newline_no_error(self, scanner):
        # 无末尾换行 + 合法语句 → 零误报（修复不破坏合法 EOF 场景）
        src = "module m;\n    assign a = b;\nendmodule"
        assert scanner.scan(src) == []


class TestEofProbe:
    """match_rule 在 token 耗尽处的 EOF 报错 + probe（截断试探）静默。

    固化 2026-08-08 修复：残缺语句（缺分号/缺 body）缺失 token 处为 EOF 时
    必选元素必须报错（不静默）；但 Level 2 消歧的截断试探（_try_parse）是
    人为截断，EOF 处应静默——否则合法 for 被误判为未识别。
    """

    def test_match_rule_reports_eof_in_real_mode(self, scanner):
        # 真实检查（probe=False）：assign 缺分号 + EOF 结尾 → 报 unexpected end
        tokens = _tokens(scanner, "assign a = b")
        prods = scanner._matcher._tree["AssignStmt"]["prods"]
        errs = []
        scanner._matcher._probe_eof = False
        scanner._matcher.match_rule(tokens, 0, prods, errs, len(tokens))
        assert any(e.code == "phase-statement" for e in errs)

    def test_match_rule_probe_silent_on_eof(self, scanner):
        # probe 语境（Level 2 截断试探）：EOF 处静默不报错
        tokens = _tokens(scanner, "assign a = b")
        prods = scanner._matcher._tree["AssignStmt"]["prods"]
        errs = []
        scanner._matcher._probe_eof = True
        scanner._matcher.match_rule(tokens, 0, prods, errs, len(tokens))
        assert errs == []


class TestStatementChecker:
    """StatementChecker 契约。"""

    def test_valid_assign_no_error(self, scanner):
        from linter.checkers.statement import StatementChecker

        tokens = _tokens(scanner, "assign a = b;")
        checker = StatementChecker("AssignStmt", 0, len(tokens), scanner._matcher)
        assert checker.validate(tokens) == []


class TestExpressionChecker:
    """ExpressionChecker 契约。"""

    def test_valid_expression_no_error(self, scanner):
        tokens = _tokens(scanner, "a + b;")
        errs, consumed = scanner._expr_checker.consume(
            tokens, 0, stop_tokens={"symbol.base.semicolon"}
        )
        assert errs == []
        assert consumed >= 3

    def test_trailing_operator_reports(self, scanner):
        # 尾随运算符（a + ;）→ phase-expr
        tokens = _tokens(scanner, "a + ;")
        errs, consumed = scanner._expr_checker.consume(
            tokens, 0, stop_tokens={"symbol.base.semicolon"}
        )
        assert any(e.code == "phase-expr" for e in errs)

    def test_invalid_start_reports(self, scanner):
        # 表达式起点非法 → phase-expr
        tokens = _tokens(scanner, "= b;")
        errs, consumed = scanner._expr_checker.consume(
            tokens, 0, stop_tokens={"symbol.base.semicolon"}
        )
        assert any(e.code == "phase-expr" for e in errs)

    def test_nested_parens_no_error(self, scanner):
        # 嵌套括号表达式完整消费、零错误
        tokens = _tokens(scanner, "a + (b * c);")
        errs, consumed = scanner._expr_checker.consume(
            tokens, 0, stop_tokens={"symbol.base.semicolon"}
        )
        assert errs == []
        assert consumed >= 6

    def test_stop_tokens_respected(self, scanner):
        # stop_tokens（逗号）生效：表达式在逗号处停止，不越过
        tokens = _tokens(scanner, "a + b , c")
        errs, consumed = scanner._expr_checker.consume(
            tokens, 0, stop_tokens={"symbol.base.comma"}
        )
        assert errs == []
        assert consumed == 3  # a + b 三个 token，逗号前停

    def test_select_atom_consumed(self, scanner):
        # 位选原子（data[3:0]）作为操作数被原子匹配消费，不吞运算符
        tokens = _tokens(scanner, "data[3:0] + 1;")
        errs, consumed = scanner._expr_checker.consume(
            tokens, 0, stop_tokens={"symbol.base.semicolon"}
        )
        assert errs == []
        assert consumed >= 5  # data [ 3 : 0 ] + 1 至少 7 token（+ 后继续）

    def test_multiline_rhs_no_false_positive(self, scanner):
        # 多行 RHS（b +\n c）：IEEE 1364 §3.1 规定换行只作 token 分隔、无语义，
        # 运算符在行尾的多行表达式必须零误报。修复：match_atom 的 consumed 从
        # 入参 i 起算（含跳过的 trivia），pratt 递归右操作数不错位。
        src = "module m;\n    assign a = b +\n        c;\nendmodule\n"
        errs = scanner.scan(src)
        assert errs == []

    def test_multiline_rhs_blocking_assign(self, scanner):
        # 过程体内多行 RHS（非阻塞赋值，含位选原子续行）
        src = (
            "module m;\n"
            "    always @(posedge clk) begin\n"
            "        q <= d +\n"
            "            {e[3:0], f};\n"
            "    end\n"
            "endmodule\n"
        )
        errs = scanner.scan(src)
        assert errs == []

    def test_multiline_rhs_nested_operator(self, scanner):
        # 多行 RHS 连续运算符链（每行末尾一个运算符），零误报
        src = (
            "module m;\n"
            "    assign a = b +\n"
            "        c *\n"
            "        d;\n"
            "endmodule\n"
        )
        errs = scanner.scan(src)
        assert errs == []

    def test_multiline_rhs_trailing_operator_still_error(self, scanner):
        # 行尾运算符但下一行是分号（真残缺 b +;）→ 仍报错（不因宽容忍漏检）
        src = "module m;\n    assign a = b +\n        ;\nendmodule\n"
        errs = scanner.scan(src)
        assert any(e.code in ("phase-expr", "phase-statement") for e in errs)
