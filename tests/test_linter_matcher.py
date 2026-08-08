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
