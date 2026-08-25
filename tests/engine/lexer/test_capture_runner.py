"""tests/engine/lexer/test_capture_runner.py — CaptureRunner：原始捕获模式抽象。

验证 lexer/capture_runner.py：
  1. 归一化：[comment] pairs（legacy）与 [capture]（新段）合并为 mode 表，
     排序保证长 start 优先；非法配置 fail-fast（decisions/0003）
  2. 三种终止 kind：line（到换行）/ marker（到标记）/ line_match（到整行）
  3. Lexer 集成：注释（legacy 路径行为等价）+ heredoc（新 capture 段），
     捕获内容内部字符不做 token 化、多行捕获行号记账正确

最小 token_define 自建（不依赖语言包）；数字形态复用全局配置
（config_loaded fixture 已加载 verilog 形态）。
"""

import pytest

from lexer.capture_runner import CaptureRunner
from lexer.lexer_utils import get_number_config
from lexer.main_lexer import Lexer


def _make_td(
    capture_modes: list[dict] | None = None,
    comment_pairs: list | None = None,
) -> dict:
    """构造最小 token_define（dict 形式，直接传 Lexer，不走 merge 校验）。"""
    td: dict = {
        "space": {"blank_space": " ", "tab": "\t", "carriage_return": "\r"},
        "newline": {"newline": "\n"},
        "symbol": {"base": {"semi": ";", "equal": "="}, "extend": {}},
        "bracket": {"pairs": [["(", ")", "parentheses"]]},
        "id": {"id": "[a-zA-Z_][a-zA-Z0-9_]*", "keyword": {"kw": "kw"}},
        "literal": {"string": "(\".*\")"},
        "comment": {"pairs": comment_pairs if comment_pairs is not None else []},
    }
    if capture_modes is not None:
        td["capture"] = capture_modes
    return td


# ═══════════════════════════════════════════════════
# 归一化（build_rules）
# ═══════════════════════════════════════════════════


class TestBuildRules:
    def test_legacy_comment_pairs_normalized(self):
        """[comment] pairs → token_type="comment"，block → marker。"""
        td = _make_td(
            comment_pairs=[["#", "\n", "line"], ["/*", "*/", "block"]]
        )
        rules = CaptureRunner.build_rules(td)
        # 排序后：/* 在前（长 start 优先），# 在后
        assert [(r.start, r.kind, r.token_type) for r in rules] == [
            ("/*", "marker", "comment"),
            ("#", "line", "comment"),
        ]

    def test_legacy_two_item_pair_defaults_line(self):
        """两元素 pair（无 kind）默认 line。"""
        td = _make_td(comment_pairs=[["//", "\n"]])
        rules = CaptureRunner.build_rules(td)
        assert len(rules) == 1
        assert rules[0].kind == "line"
        assert rules[0].token_type == "comment"

    def test_long_start_sorted_first(self):
        """长 start 优先：<<EOF 在 << 前（heredoc 形态）。"""
        td = _make_td(
            capture_modes=[
                {
                    "start": "<<",
                    "end": ";",
                    "kind": "marker",
                    "token_type": "symbol.extend.shift",
                },
                {
                    "start": "<<EOF",
                    "end": "EOF",
                    "kind": "line_match",
                    "token_type": "literal.heredoc",
                },
            ]
        )
        starts = [r.start for r in CaptureRunner.build_rules(td)]
        assert starts == ["<<EOF", "<<"]

    def test_invalid_legacy_kind_fails_fast(self):
        """legacy [comment] 非法 kind → ValueError（fail-fast，不静默降级）。"""
        td = _make_td(comment_pairs=[["#", "\n", "bogus"]])
        with pytest.raises(ValueError, match="未知 kind"):
            CaptureRunner.build_rules(td)

    def test_capture_missing_end_fails_fast(self):
        """marker/line_match 缺 end → ValueError。"""
        td = _make_td(
            capture_modes=[
                {"start": "/*", "kind": "marker", "token_type": "comment"}
            ]
        )
        with pytest.raises(ValueError, match="非空 end"):
            CaptureRunner.build_rules(td)

    def test_capture_invalid_kind_fails_fast(self):
        """[capture] 非法 kind → ValueError。"""
        td = _make_td(
            capture_modes=[
                {"start": "#", "end": "", "kind": "bogus", "token_type": "x"}
            ]
        )
        with pytest.raises(ValueError, match="配置不完整"):
            CaptureRunner.build_rules(td)


# ═══════════════════════════════════════════════════
# run 直接测试（三种终止 kind）
# ═══════════════════════════════════════════════════


class TestRunLine:
    def test_line_stops_before_newline(self):
        """line：到换行停止，换行不消费。"""
        td = _make_td(comment_pairs=[["#", "\n", "line"]])
        result = CaptureRunner.run("# note\nnext", 0, td)
        assert result is not None
        content, pos, token_type = result
        assert content == "# note"
        assert pos == 6  # 停在 \n 前
        assert token_type == "comment"

    def test_line_to_eof(self):
        td = _make_td(comment_pairs=[["#", "\n", "line"]])
        result = CaptureRunner.run("# tail", 0, td)
        assert result is not None
        content, _, token_type = result
        assert content == "# tail"
        assert token_type == "comment"

    def test_no_match_returns_none(self):
        td = _make_td(comment_pairs=[["#", "\n", "line"]])
        assert CaptureRunner.run("abc", 0, td) is None


class TestRunMarker:
    def test_marker_closed(self):
        td = _make_td(comment_pairs=[["/*", "*/", "block"]])
        result = CaptureRunner.run("/* x */ tail", 0, td)
        assert result is not None
        content, pos, token_type = result
        assert content == "/* x */"
        assert token_type == "comment"
        assert pos == 7  # 消费到 */ 之后

    def test_marker_unclosed_to_eof(self):
        """未闭合 marker：EOF 自然终止（与 legacy 行为一致）。"""
        td = _make_td(comment_pairs=[["/*", "*/", "block"]])
        result = CaptureRunner.run("/* unclosed", 0, td)
        assert result is not None
        content, _, token_type = result
        assert content == "/* unclosed"
        assert token_type == "comment"


class TestRunLineMatch:
    _HEREDOC_TD = _make_td(
        capture_modes=[
            {
                "start": "<<EOF",
                "end": "EOF",
                "kind": "line_match",
                "token_type": "literal.heredoc",
            }
        ]
    )

    def test_line_match_terminates_on_full_line(self):
        result = CaptureRunner.run(
            "<<EOF\nline1\nline2\nEOF\nnext", 0, self._HEREDOC_TD
        )
        assert result is not None
        content, pos, token_type = result
        assert content == "<<EOF\nline1\nline2\n"  # 不消费 EOF 行
        assert token_type == "literal.heredoc"
        assert pos == len("<<EOF\nline1\nline2\n")

    def test_line_match_requires_line_start(self):
        """内容行内出现的 end 标记不算终止（须独立成行）。"""
        result = CaptureRunner.run(
            "<<EOF\na EOF b\nEOF\n", 0, self._HEREDOC_TD
        )
        assert result is not None
        content, _, _ = result
        assert content == "<<EOF\na EOF b\n"

    def test_line_match_unclosed_to_eof(self):
        result = CaptureRunner.run(
            "<<EOF\nonly one line", 0, self._HEREDOC_TD
        )
        assert result is not None
        content, _, token_type = result
        assert content == "<<EOF\nonly one line"
        assert token_type == "literal.heredoc"


# ═══════════════════════════════════════════════════
# Lexer 集成（heredoc + legacy comment 共存）
# ═══════════════════════════════════════════════════


def _lexer_with(td: dict) -> Lexer:
    """自建 token_define 的 Lexer（数字形态复用全局 verilog 配置）。"""
    return Lexer(token_define_dict=td, number_configs=get_number_config())


class TestLexerIntegration:
    def test_heredoc_content_not_tokenized(self, config_loaded):
        """heredoc 内容里 # $ / 原样保留，不触发注释/符号/unrecognized。"""
        td = _make_td(
            capture_modes=[
                {
                    "start": "<<EOF",
                    "end": "EOF",
                    "kind": "line_match",
                    "token_type": "literal.heredoc",
                }
            ]
        )
        lexer = _lexer_with(td)
        tokens = lexer.tokenize("x = <<EOF\nrun $a / #b\nEOF\ny = 1\n")
        types = [t.type for t in tokens]
        assert "literal.heredoc" in types
        heredoc = next(t for t in tokens if t.type == "literal.heredoc")
        assert heredoc.content == "<<EOF\nrun $a / #b\n"
        # heredoc 后正常 token 继续
        assert types[-2] == "literal.number"

    def test_heredoc_token_line_accounting(self, config_loaded):
        """多行捕获后，后续 token 行号正确（行号记账）。"""
        td = _make_td(
            capture_modes=[
                {
                    "start": "<<EOF",
                    "end": "EOF",
                    "kind": "line_match",
                    "token_type": "literal.heredoc",
                }
            ]
        )
        lexer = _lexer_with(td)
        tokens = lexer.tokenize("x = <<EOF\na\nb\nEOF\ny = 1\n")
        after = next(
            t for t in tokens if t.type == "id" and t.content == "y"
        )
        assert after.line == 5  # 第 5 行（heredoc 跨 1-4 行）

    def test_legacy_comment_and_capture_coexist(self, config_loaded):
        """legacy [comment] 与新 [capture] 段共存，互不干扰。"""
        td = _make_td(
            comment_pairs=[["#", "\n", "line"]],
            capture_modes=[
                {
                    "start": "<<EOF",
                    "end": "EOF",
                    "kind": "line_match",
                    "token_type": "literal.heredoc",
                }
            ],
        )
        lexer = _lexer_with(td)
        tokens = lexer.tokenize("# note\nx = <<EOF\nhi\nEOF\n")
        types = [t.type for t in tokens]
        assert types[0] == "comment"
        assert "literal.heredoc" in types

    def test_block_comment_multiline_accounting(self, config_loaded):
        """legacy 块注释多行记账保持等价（回归：既有行为）。"""
        td = _make_td(comment_pairs=[["/*", "*/", "block"]])
        lexer = _lexer_with(td)
        tokens = lexer.tokenize("/* a\nb */\nx = 1\n")
        x = next(t for t in tokens if t.content == "x")
        assert x.line == 3
