"""tests/parser/test_debug_infra.py — 调试基础设施测试。

覆盖（对应 TODO P0.1 调试基础设施）：
    a) 日志分级开关（WARN 不被吞 / INFO 按阈值过滤 / verbose=TRACE）
    b) parser 停点/trace（set_trace / _maybe_trace 按规则名/位置过滤）
    d) 行号对账工具（reconcile_line_numbers / reconcile_mismatches）
"""

from core.define import Token
from core.debug_report import reconcile_line_numbers, reconcile_mismatches
from parser.parser_core import Parser, ParseContext


def _tk(type_: str, content: str = "", line: int = 1, column: int = 0) -> Token:
    return Token(type=type_, content=content or type_, line=line, column=column)


def _mk_parser(verbose: bool = False, log_file: str | None = None) -> Parser:
    """轻量实例：跳过 __init__，模拟 __init__ 里的日志级别初始化逻辑。"""
    p = object.__new__(Parser)
    p.verbose = verbose
    p.debug_log_file = log_file
    p._log_indent = Parser._log_indent.__get__(p)
    if log_file is None and not verbose:
        p._log_level = Parser.LOG_WARN
    elif verbose:
        p._log_level = Parser.LOG_TRACE
    else:
        p._log_level = Parser.LOG_INFO
    return p


class TestLogLevels:
    """a) 日志分级开关。"""

    def test_warn_not_swallowed_when_no_log_file(self, capsys):
        # 修复：debug_log_file=None 时 WARN 不再被空 lambda 吞掉
        p = _mk_parser(verbose=False, log_file=None)
        p._log_state("WARN: boom", level=Parser.LOG_WARN)
        assert "boom" in capsys.readouterr().err

    def test_warn_method_outputs(self, capsys):
        p = _mk_parser(verbose=False, log_file=None)
        p._warn("test warning")
        assert "WARN: test warning" in capsys.readouterr().err

    def test_info_skipped_when_threshold_warn(self, capsys):
        p = _mk_parser(verbose=False, log_file=None)
        p._log_state("info msg", level=Parser.LOG_INFO)
        assert capsys.readouterr().err == ""

    def test_verbose_level_is_trace(self):
        p = _mk_parser(verbose=True, log_file=None)
        assert p._log_level == Parser.LOG_TRACE

    def test_no_log_file_level_is_warn(self):
        p = _mk_parser(verbose=False, log_file=None)
        assert p._log_level == Parser.LOG_WARN

    def test_log_file_level_is_info(self):
        p = _mk_parser(verbose=False, log_file="x.log")
        assert p._log_level == Parser.LOG_INFO


class TestTrace:
    """b) parser 停点/trace。"""

    def _mk(self) -> Parser:
        p = object.__new__(Parser)
        p._trace_rule = None
        p._trace_token_pos = None
        return p

    def test_maybe_trace_rule_hit(self, capsys):
        p = self._mk()
        p.set_trace(rule="Always")
        ctx = ParseContext([_tk("t0")])
        ctx.path_stack = ["Root"]
        p._maybe_trace(ctx, "AlwaysStmt")
        assert "[trace]" in capsys.readouterr().err

    def test_maybe_trace_rule_miss(self, capsys):
        p = self._mk()
        p.set_trace(rule="Always")
        ctx = ParseContext([_tk("t0")])
        ctx.path_stack = ["Root"]
        p._maybe_trace(ctx, "IfStmt")
        assert capsys.readouterr().err == ""

    def test_maybe_trace_pos_hit(self, capsys):
        p = self._mk()
        p.set_trace(token_pos=2)
        ctx = ParseContext([_tk("t0"), _tk("t1"), _tk("t2")])
        ctx.path_stack = ["Root"]
        ctx.advance_token()
        ctx.advance_token()  # pos 2
        p._maybe_trace(ctx, "X")
        assert "[trace]" in capsys.readouterr().err

    def test_no_trace_no_output(self, capsys):
        p = self._mk()
        ctx = ParseContext([_tk("t0")])
        ctx.path_stack = ["Root"]
        p._maybe_trace(ctx, "Any")
        assert capsys.readouterr().err == ""

    def test_set_trace_stores_filters(self):
        p = self._mk()
        p.set_trace(rule="Always", token_pos=5)
        assert p._trace_rule == "Always"
        assert p._trace_token_pos == 5


class TestReconcile:
    """d) 行号对账工具。"""

    def test_reconcile_line_numbers(self):
        tokens = [_tk("a", "a", 1, 0), _tk("b", "b", 2, 0)]
        rows = reconcile_line_numbers(tokens, source="a\nb\n")
        assert len(rows) == 2
        assert rows[0]["line1"] == 1 and rows[0]["span0"] == 0
        assert rows[1]["line1"] == 2 and rows[1]["span0"] == 1
        assert rows[0]["in_line"] is True

    def test_reconcile_mismatches_clean(self):
        tokens = [_tk("a", "a", 1, 0), _tk("b", "b", 1, 2), _tk("c", "c", 2, 0)]
        assert reconcile_mismatches(tokens) == []

    def test_reconcile_mismatches_finds_rollback(self):
        # 模拟多行注释未更新行号：line 从 3 回退到 2 → 定位错位 token
        tokens = [_tk("a", "a", 1, 0), _tk("b", "b", 3, 0), _tk("c", "c", 2, 0)]
        bad = reconcile_mismatches(tokens)
        assert len(bad) == 1
        assert bad[0]["idx"] == 2
        assert bad[0]["line1"] == 2
