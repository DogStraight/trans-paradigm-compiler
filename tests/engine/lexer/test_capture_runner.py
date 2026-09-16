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
from lexer.main_lexer import Lexer, _build_unsized_prefixes


def _make_td(
    capture_modes: list[dict] | None = None,
    comment_pairs: list | None = None,
    string_delims: list | None = None,
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
    if string_delims is not None:
        td["string"] = {"delimiters": string_delims}
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

    def test_capture_after_and_next_chars_parsed(self):
        """after（token 类型列表）与 next_chars（字符集）解析进规则。"""
        td = _make_td(
            capture_modes=[
                {
                    "start": "|",
                    "kind": "indent_leq",
                    "token_type": "literal.block_scalar",
                    "after": ["symbol.base.colon", "symbol.base.sub"],
                    "next_chars": " \t\n+-",
                }
            ]
        )
        rules = CaptureRunner.build_rules(td)
        rule = rules[0]
        assert rule.after == ("symbol.base.colon", "symbol.base.sub")
        assert rule.next_set == frozenset(" \t\n+-")

    def test_capture_indent_leq_needs_no_end(self):
        """indent_leq 无需 end（终止条件是列比较，base_col 运行时传入）。"""
        td = _make_td(
            capture_modes=[
                {"start": "|", "kind": "indent_leq", "token_type": "x"}
            ]
        )
        assert len(CaptureRunner.build_rules(td)) == 1


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


class TestRunDelim:
    """delim kind：字符串定界符（[string] delimiters）。"""

    def _td(self, delimiters):
        td = _make_td()
        td["string"] = {"delimiters": delimiters}
        return td

    def test_delim_closed(self):
        """到闭合定界符（消费，含定界符本身）。"""
        td = self._td(['"'])
        result = CaptureRunner.run('"abc" tail', 0, td)
        assert result is not None
        content, pos, token_type = result
        assert content == '"abc"'
        assert pos == 5
        assert token_type == "literal.string"

    def test_delim_stops_at_newline_without_consuming(self):
        """未闭合遇换行：不消费换行（字符串不跨行）。"""
        td = self._td(['"'])
        result = CaptureRunner.run('"hello\nnext', 0, td)
        assert result is not None
        content, pos, _ = result
        assert content == '"hello'
        assert pos == len('"hello')  # 停在 \n 前

    def test_delim_unclosed_to_eof(self):
        td = self._td(['"'])
        result = CaptureRunner.run('"tail', 0, td)
        assert result is not None
        content, _, token_type = result
        assert content == '"tail'
        assert token_type == "literal.string"

    def test_single_quote_delim(self):
        """单引号定界符（yaml/c4）。"""
        td = self._td(['"', "'"])
        result = CaptureRunner.run("'hello'", 0, td)
        assert result is not None
        content, _, _ = result
        assert content == "'hello'"

    def test_delim_multi_char_closed(self):
        """多字符定界符（`\"\"\"`）：终止判定按长度比较。

        曾按单字符比较（`ch == rule.end`）→ 永不匹配，静默吞到行尾/EOF
        （把后续 token 一起吃进字符串）。
        """
        td = self._td(['"""'])
        result = CaptureRunner.run('"""abc""" tail', 0, td)
        assert result is not None
        content, pos, token_type = result
        assert content == '"""abc"""'
        assert pos == 9  # 不吞后面的 tail
        assert token_type == "literal.string"

    def test_delim_multi_char_stops_at_newline(self):
        """多字符定界符未闭合遇换行：同样不跨行。"""
        td = self._td(['"""'])
        result = CaptureRunner.run('"""abc\nnext', 0, td)
        assert result is not None
        content, pos, _ = result
        assert content == '"""abc'
        assert pos == 6

    def test_delim_multi_char_longest_start_wins(self):
        """`"` 与 `\"\"\"` 并存：长 start 优先（不把 `\"\"\"` 拆成 `"`+`"`）。"""
        td = self._td(['"', '"""'])
        rules = CaptureRunner.build_rules(td)
        assert [r.start for r in rules if r.kind == "delim"] == ['"""', '"']
        result = CaptureRunner.run('"""abc"""', 0, td)
        assert result is not None and result[0] == '"""abc"""'

    def test_build_rules_expands_delimiters(self):
        """[string] delimiters 展开为 delim 规则（token_type = literal.string）。"""
        td = self._td(['"', "'"])
        rules = CaptureRunner.build_rules(td)
        delim_rules = [r for r in rules if r.kind == "delim"]
        assert [(r.start, r.end, r.token_type) for r in delim_rules] == [
            ('"', '"', "literal.string"),
            ("'", "'", "literal.string"),
        ]

    def test_invalid_delimiter_fails_fast(self):
        """空定界符 → ValueError（fail-fast）。"""
        td = self._td([""])
        with pytest.raises(ValueError, match="非法条目"):
            CaptureRunner.build_rules(td)


class TestRunIndentLeq:
    """indent_leq kind：YAML 块标量（列比较终止）。"""

    _TD = _make_td(
        capture_modes=[
            {"start": "|", "kind": "indent_leq", "token_type": "literal.block_scalar"}
        ]
    )

    def test_basic_content(self):
        """指示符行 + 更深缩进的内容行；剥尾部换行。"""
        result = CaptureRunner.run("|\n  line1\n  line2\nnext", 0, self._TD, 0)
        assert result is not None
        content, pos, token_type = result
        assert content == "|\n  line1\n  line2"
        assert token_type == "literal.block_scalar"
        assert pos == len("|\n  line1\n  line2\n")  # 停在 next 前

    def test_terminates_at_base_col(self):
        """内容行列 ≤ 基准列即终止（基准=2）。"""
        result = CaptureRunner.run("|\n    a\n  b\n", 0, self._TD, 2)
        assert result is not None
        content, pos, _ = result
        assert content == "|\n    a"
        assert pos == len("|\n    a\n")  # 停在 "  b" 前

    def test_blank_lines_are_content(self):
        """空行（仅空白）是内容。"""
        result = CaptureRunner.run("|\n  a\n\n  b\nnext", 0, self._TD, 0)
        assert result is not None
        content, _, _ = result
        assert content == "|\n  a\n\n  b"

    def test_eof_termination(self):
        """无终止行时到 EOF 自然终止。"""
        result = CaptureRunner.run("|\n  a\n  b", 0, self._TD, 0)
        assert result is not None
        content, _, _ = result
        assert content == "|\n  a\n  b"  # EOF 无尾部换行可剥

    def test_chomping_and_indent_indicators_verbatim(self):
        """切块（|-/|+）与缩进指示（|2）原样保留。"""
        result = CaptureRunner.run("|+\n  a\nnext", 0, self._TD, 0)
        assert result is not None
        assert result[0] == "|+\n  a"
        result2 = CaptureRunner.run("|2\n   two\nnext", 0, self._TD, 0)
        assert result2 is not None
        assert result2[0] == "|2\n   two"

    def test_crlf_content_verbatim(self):
        """CRLF 内容原样保留（\r 是 [space] 成员，不吞）。"""
        result = CaptureRunner.run("|\r\n  a\r\n  b\r\nnext", 0, self._TD, 0)
        assert result is not None
        content, _, _ = result
        assert content == "|\r\n  a\r\n  b\r"  # 剥 \n 后尾 \r 保留

    def test_immediate_termination_empty_block(self):
        """指示符后立即遇到 ≤ 基准的行 → 空块。"""
        result = CaptureRunner.run("|\nnext", 0, self._TD, 0)
        assert result is not None
        content, pos, _ = result
        assert content == "|"
        assert pos == len("|\n")


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


class TestUnsizedPrefixes:
    """无尺寸数字触发前缀配置化（_build_unsized_prefixes）。"""

    def test_verilog_style_quote_bases(self):
        """size=none + 单字符前缀：prefix+base 大小写变体。"""
        configs = [
            {
                "size": "none",
                "base_prefix": "'",
                "bases": ["d", "b", "o", "h"],
            }
        ]
        chars = _build_unsized_prefixes(configs)
        assert chars == {"'d", "'D", "'b", "'B", "'o", "'O", "'h", "'H"}

    def test_signed_adds_quote_s(self):
        configs = [
            {
                "size": "none",
                "base_prefix": "'",
                "bases": ["d"],
                "signed": True,
            }
        ]
        chars = _build_unsized_prefixes(configs)
        assert chars == {"'d", "'D", "'s", "'S"}

    def test_sized_and_multichar_prefix_skipped(self):
        """带 size 形态与多字符前缀（0x）不产生触发。"""
        configs = [
            {"size": {"digits": "nonzero"}, "base_prefix": "'", "bases": ["h"]},
            {"size": "none", "base_prefix": "0x", "bases": []},
            {"size": "none", "base_prefix": "none", "bases": []},
        ]
        assert _build_unsized_prefixes(configs) == set()

    def test_none_configs_empty(self):
        assert _build_unsized_prefixes(None) == set()


class TestLexerIntegration:
    def test_heredoc_content_not_tokenized(self, config_loaded):
        """heredoc 内容里 # $ / 原样保留，不触发注释/符号/unrecognized。"""
        del config_loaded  # fixture 依赖声明（配置加载）
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

    def test_multi_char_delimiter_keeps_trailing_tokens(self, config_loaded):
        """多字符字符串定界符：闭合后行内后续 token 不被吞掉（集成）。"""
        del config_loaded  # fixture 依赖声明（配置加载）
        td = _make_td(string_delims=['"""'])
        lexer = _lexer_with(td)
        tokens = lexer.tokenize('x = """ab""" y')
        types = [t.type for t in tokens]
        assert "literal.string" in types
        s = next(t for t in tokens if t.type == "literal.string")
        assert s.content == '"""ab"""'
        # 后续 y 仍被识别为 id（曾整行被吞进字符串）
        assert any(t.type == "id" and t.content == "y" for t in tokens)

    def test_heredoc_token_line_accounting(self, config_loaded):
        """多行捕获后，后续 token 行号正确（行号记账）。"""
        del config_loaded  # fixture 依赖声明（配置加载）
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
        del config_loaded  # fixture 依赖声明（配置加载）
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
        del config_loaded  # fixture 依赖声明（配置加载）
        td = _make_td(comment_pairs=[["/*", "*/", "block"]])
        lexer = _lexer_with(td)
        tokens = lexer.tokenize("/* a\nb */\nx = 1\n")
        x = next(t for t in tokens if t.content == "x")
        assert x.line == 3

    def test_line_terminating_comment_starts_from_declaration(self, config_loaded):
        """行终止型注释起点只由声明给出（kind = line；block → marker 不算）。

        渲染阶段据此判断"行尾注释后必须换行"——引擎不得硬编码注释标点。
        """
        del config_loaded  # fixture 依赖声明（配置加载）
        td = _make_td(comment_pairs=[["#", "\n", "line"], ["/*", "*/", "block"]])
        assert _lexer_with(td).line_terminating_comment_starts() == ("#",)

    def test_no_comment_declaration_means_empty_starts(self, config_loaded):
        """无注释声明 → 空词表（引擎零语言知识）。"""
        del config_loaded  # fixture 依赖声明（配置加载）
        assert _lexer_with(_make_td()).line_terminating_comment_starts() == ()
