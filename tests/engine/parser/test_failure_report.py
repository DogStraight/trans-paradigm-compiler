"""tests/parser/test_failure_report.py — 失败现场报告机制测试。

覆盖：
    core.debug_report 纯函数（token 窗口 / 报告组装 / 渲染）
    Parser._record_fail_site / _dump_failure_report（轻量实例，不依赖语法加载）
    真实 Parser 解析坏输入 → _last_failure_report 非空（集成）
"""

import pytest

from core.define import Token, DEFAULT_RULES_DIR
from core.debug_report import (
    token_summary,
    format_token_window,
    build_failure_report,
    render_failure_report,
)
from parser.parser_core import Parser, ParseContext


def _tk(type_: str, content: str = "", line: int = 1, column: int = 0) -> Token:
    """创建合成 Token。"""
    return Token(type=type_, content=content or type_, line=line, column=column)


# ── core.debug_report 纯函数 ─────────────────────────────

class TestDebugReport:
    def test_token_summary(self):
        t = _tk("keyword.foo", "foo", 3, 5)
        assert token_summary(t) == "'foo':keyword.foo@3:5"

    def test_token_summary_eof(self):
        assert token_summary(None) == "<EOF>"

    def test_window_marks_current_and_shows_context(self):
        tokens = [_tk(f"t{i}") for i in range(10)]
        w = format_token_window(tokens, 5)
        assert ">>" in w
        assert "'t5'" in w
        assert "'t2'" in w  # before=3 → t2..t8
        assert "'t8'" in w
        assert "'t1'" not in w

    def test_window_truncation_marks(self):
        tokens = [_tk(f"t{i}") for i in range(10)]
        w = format_token_window(tokens, 0, before=3, after=3)
        # pos=0 → 窗口 t0..t3（当前 + after=3），剩余 6 个
        assert "... (6 after)" in w
        assert "before" not in w

    def test_window_at_eof(self):
        tokens = [_tk(f"t{i}") for i in range(3)]
        w = format_token_window(tokens, 5)
        assert "'t2'" in w
        assert "after" not in w

    def test_window_empty(self):
        assert format_token_window([], 0) == "<empty token stream>"

    def test_build_report_fields(self):
        tokens = [_tk(f"t{i}") for i in range(5)]
        r = build_failure_report(
            position=2, tokens=tokens, reason="boom", rule="Foo", path="Root/Foo"
        )
        assert r["position"] == 2
        assert r["reason"] == "boom"
        assert r["rule"] == "Foo"
        assert r["path"] == "Root/Foo"
        assert "window" in r
        assert ">>" in r["window"]

    def test_build_report_skips_empty_optional_fields(self):
        r = build_failure_report(position=0, tokens=None)
        assert r["token"] == "<EOF>"
        assert "rule" not in r
        assert "reason" not in r

    def test_render_report_ascii_only(self):
        r = {"position": 1, "token": "'x'", "window": "w"}
        out = render_failure_report(r)
        assert "failure site" in out
        assert "position: 1" in out
        # 全 ASCII，避免 Windows 默认 GBK 控制台乱码
        assert all(ord(c) < 128 for c in out)

    def test_render_sanitizes_non_ascii(self):
        # 中文 token 内容 / reason（如 pratt 异常消息）在渲染层被替换为 ?，
        # 控制台输出必然 ASCII；原始信息仍在报告 dict 中
        r = {"position": 0, "token": "'中文':id@1:0", "reason": "表达式不完整"}
        out = render_failure_report(r)
        assert all(ord(c) < 128 for c in out)
        assert "?" in out
        # 程序化访问保留原始信息
        assert r["reason"] == "表达式不完整"


# ── Parser._record_fail_site / _dump_failure_report ───────

class TestParserFailSite:
    def _mk_parser(self) -> Parser:
        """轻量实例：跳过 __init__（不依赖语法/配置加载）。"""
        p = object.__new__(Parser)
        p._fail_sites = {}
        p._last_failure_report = None
        p.verbose = False
        p.debug_log_file = None
        return p

    def test_record_aggregates_by_position(self):
        p = self._mk_parser()
        ctx = ParseContext([_tk("t0"), _tk("t1")])
        ctx.path_stack = ["Root"]
        p._record_fail_site(ctx, rule="A", reason="r1")  # pos 0
        ctx.advance_token()
        p._record_fail_site(ctx, rule="B", reason="r2")  # pos 1
        p._record_fail_site(ctx, rule="B2", reason="r2b")  # pos 1 覆盖
        assert len(p._fail_sites) == 2
        assert p._fail_sites[1]["rule"] == "B2"
        assert p._fail_sites[0]["path"] == "Root"

    def test_record_preserve_keeps_specific_site(self):
        p = self._mk_parser()
        ctx = ParseContext([_tk("t0")])
        ctx.path_stack = ["Root"]
        # 下层具体记录（候选规则名）
        p._record_fail_site(
            ctx, rule="BlockingAssign", reason="all sentence candidates failed"
        )
        # 上层泛化记录（preserve=True）不覆盖
        p._record_fail_site(
            ctx, rule="sentence", reason="block body stop", preserve=True
        )
        assert p._fail_sites[0]["rule"] == "BlockingAssign"

    def test_dump_report_builds_last_report(self, capsys):
        p = self._mk_parser()
        tokens = [_tk("a", "a", 1, 0), _tk("b", "b", 1, 2), _tk("c", "c", 1, 4)]
        ctx = ParseContext(tokens)
        ctx.path_stack = ["Root"]
        ctx.advance_token()  # 失败在 pos 1
        p._record_fail_site(ctx, rule="StmtX", reason="production match failed")
        p._dump_failure_report(ctx, reason="final")
        r = p._last_failure_report
        assert r is not None
        assert r["position"] == 1
        assert r["rule"] == "StmtX"
        assert r["reason"] == "final"  # 显式 reason 优先于 fail site
        assert ">>" in r["window"]
        assert "'b'" in r["window"]
        # 报告打印到 stderr（ASCII，无乱码）
        captured = capsys.readouterr()
        assert "failure site" in captured.err

    def test_dump_falls_back_to_nearest_site(self, capsys):
        p = self._mk_parser()
        tokens = [_tk("a", "a", 1, 0), _tk("b", "b", 1, 2), _tk("c", "c", 1, 4)]
        ctx = ParseContext(tokens)
        ctx.path_stack = ["Root"]
        ctx.advance_token()  # 到 pos 1
        p._record_fail_site(ctx, rule="StmtX", reason="production match failed")
        ctx.advance_token()  # 最终停在 pos 2（该位置无记录）
        p._dump_failure_report(ctx)
        r = p._last_failure_report
        assert r is not None
        assert r["rule"] == "StmtX"  # 回退到最近失败现场
        assert r["reason"] == "production match failed"


# ── 真实 Parser 集成：坏输入 → 报告非空 ─────────────────

class TestParserIntegration:
    def _build_parser(self, config_loaded):
        from core.define import GrammarRulesRegister
        from parser import setup_grammar
        from parser.rule_selector import RuleSelector

        rules = setup_grammar(DEFAULT_RULES_DIR, GrammarRulesRegister.get_default())
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rs = RuleSelector(rules, stmt_names)
        return Parser(
            rules_dir=DEFAULT_RULES_DIR,
            rules=rules,
            rule_selector=rs,
            log_file="",
        )

    def test_parse_broken_input_sets_report(self, config_loaded, capsys):
        from lexer import Lexer

        p = self._build_parser(config_loaded)
        lexer = Lexer(rules_dir=DEFAULT_RULES_DIR)
        # 坏输入：端口列表未闭合
        tokens = lexer.tokenize("module broken (\n  input wire a,\n")
        p.parse(tokens)
        assert p._last_failure_report is not None, "坏输入应产出失败现场报告"
        r = p._last_failure_report
        assert "position" in r
        assert "window" in r
        # 报告含 token 窗口与失败点信息（ASCII 输出）
        captured = capsys.readouterr()
        assert "failure site" in captured.err
