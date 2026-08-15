"""tests/parser/test_real_syntax.py — 真实项目（tv80/darkriscv）暴露的语法缺口回归。

每个用例对应一个真实样本触发过的解析失败，防回归：
    tv80：位置参数实例化 / 空端口连接 / 非 ANSI 端口列表 / body parameter 声明 /
         多行敏感列表 / 单语句 if + else + end 行内注释
    darkriscv：pratt `:` 后 newline + `!` 前缀（三目链续行）
"""

import pytest

from core.define import DEFAULT_RULES_DIR
from parser import setup_grammar
from parser.parser_core import Parser
from parser.rule_selector import RuleSelector
from core.define import GrammarRulesRegister
from lexer import Lexer


@pytest.fixture(scope="module")
def parser(config_loaded):
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


@pytest.fixture(scope="module")
def lex(config_loaded):
    return Lexer(rules_dir=DEFAULT_RULES_DIR)


def _assert_ok(parser, lex, src):
    tokens = lex.tokenize(src)
    parser.parse(tokens)
    assert not parser._parse_truncated, "完整解析应无 truncated"


def _module_body(parser, lex, body):
    _assert_ok(parser, lex, "module m;\n" + body + "\nendmodule\n")


# ── tv80：位置参数实例化 ──


class TestPositionalParams:
    def test_positional_params(self, parser, lex):
        """`#(Mode, IOWait)` 位置参数（无 .name() 前缀）。"""
        _module_body(
            parser,
            lex,
            "tv80_core #(Mode, IOWait) i_tv80_core (\n"
            "    .cen(cen),\n    .di(di)\n);",
        )

    def test_mixed_params(self, parser, lex):
        """命名 + 位置混合参数。"""
        _module_body(
            parser,
            lex,
            "foo #(.A(1), B, .C(2)) u (\n    .x(x)\n);",
        )


# ── tv80：空端口连接 .name() ──


class TestEmptyPort:
    def test_empty_port_connect(self, parser, lex):
        """`.IntE ()` AUTOARG 风格未连接端口（@Expression 可空）。"""
        _module_body(
            parser,
            lex,
            "tv80_core #(Mode) i_tv80_core (\n"
            "    .IntE (),\n    .cen(cen)\n);",
        )


# ── tv80：非 ANSI 端口列表 ──


class TestNonAnsiPorts:
    def test_bare_port_names(self, parser, lex):
        """模块头括号内裸端口名列表（方向/类型在 body 声明）。"""
        _assert_ok(
            parser,
            lex,
            "module tv80s (\n"
            "    m1_n, iorq, write,\n"
            "    reset_n, clk\n"
            ");\n"
            "    input reset_n;\n"
            "    output m1_n;\n"
            "endmodule\n",
        )

    def test_body_port_decls(self, parser, lex):
        """body 端口声明（input/output 带 range 与行内注释）。"""
        _module_body(
            parser,
            lex,
            "input [7:0] IR;\n"
            "output [2:0] MCycles ; // comment\n"
            "output Inc_PC;\n",
        )


# ── tv80：body parameter 声明 ──


class TestBodyParamDecl:
    def test_parameter_in_body(self, parser, lex):
        """module body 的 `parameter X = 0;`（非 localparam）。"""
        _module_body(
            parser,
            lex,
            "parameter Mode = 0; // comment\n"
            "parameter Flag_C = 0;\n"
            "localparam Local = 1;\n",
        )


# ── tv80：多行敏感列表 ──


class TestMultiLineSensitivity:
    def test_sensitivity_across_lines(self, parser, lex):
        """`@ (a or b\\n or c)` 敏感列表跨行（repeat 内 seq/choice 跳 newline）。"""
        _module_body(
            parser,
            lex,
            "always @ (/*AUTOSENSE*/a or b\n"
            "            or c or d)\n"
            "    begin\n"
            "        q = a;\n"
            "    end",
        )


# ── tv80：单语句 if + else + end 行内注释 ──


class TestIfElseEndComment:
    def test_single_stmt_if_else_end_comment(self, parser, lex):
        """`if (A) X = 1; else begin ... end // c`：块结束符后行内注释被消费。"""
        _module_body(
            parser,
            lex,
            "always @* begin\n"
            "    if (A) X = 1;\n"
            "    else if (B)\n"
            "        begin\n"
            "            Y = 2;\n"
            "        end // comment\n"
            "end",
        )

    def test_else_begin_end_comment(self, parser, lex):
        """else begin 块 + end 行尾注释。"""
        _module_body(
            parser,
            lex,
            "always @* begin\n"
            "    if (A) X = 1; else begin Y = 2; end // c\n"
            "end",
        )


# ── darkriscv：pratt 三目链 `:` 后 newline + `!` 前缀 ──


class TestTernaryPrefixAfterNewline:
    def test_not_prefix_after_colon_newline(self, parser, lex):
        """`: \\n !F7[5] ? ...`：三目链续行行首一元 `!`（前缀解析跳 newline）。"""
        _module_body(
            parser,
            lex,
            "wire [31:0] RMDATA =\n"
            "    A ? A :\n"
            "    !F7[5] ? A :\n"
            "              S1REG;",
        )

    def test_full_ternary_chain(self, parser, lex):
        """darkriscv RMDATA 完整三目链（9 分支 + $signed + >>>）。"""
        _module_body(
            parser,
            lex,
            "wire [31:0] RMDATA =\n"
            "    FCT3==7 ? U1REG&S2REGX :\n"
            "    FCT3==6 ? U1REG|S2REGX :\n"
            "    FCT3==4 ? U1REG^S2REGX :\n"
            "    FCT3==3 ? U1REG<U2REGX :\n"
            "    FCT3==2 ? S1REG<S2REGX :\n"
            "    FCT3==0 ? (XRCC&&FCT7[5] ? U1REG-S2REGX : U1REG+S2REGX) :\n"
            "    FCT3==1 ? S1REG<<U2REGX[4:0] :\n"
            "    !FCT7[5] ? S1REG>>U2REGX[4:0] :\n"
            "              $signed(S1REG>>>U2REGX[4:0]);",
        )
