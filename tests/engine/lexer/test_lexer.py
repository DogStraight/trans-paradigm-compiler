"""Lexer 单元测试 — token 化正确性 + 边界条件 + token classifier。"""

import pytest
from core.define import Token

# ═══════════════════════════════════════════════════════
# 基础 token 化
# ═══════════════════════════════════════════════════════


class TestTokenizeBasic:
    """基础 Verilog 结构的 token 化正确性。"""

    def test_empty_module(self, lexer):
        """module m; endmodule → 4 tokens。"""
        tokens = lexer.tokenize("module m; endmodule")
        types = [t.type for t in tokens]
        assert types == [
            "keyword.module",
            "id",
            "symbol.base.semicolon",
            "keyword.endmodule",
        ]

    def test_wire_declaration(self, lexer):
        """wire a; → keyword.wire + id + semicolon。"""
        tokens = lexer.tokenize("wire a;")
        assert len(tokens) == 3
        assert tokens[0].type == "keyword.wire"
        assert tokens[1].type == "id"
        assert tokens[1].content == "a"
        assert tokens[2].type == "symbol.base.semicolon"

    def test_reg_declaration(self, lexer):
        """reg [7:0] data; → keyword.reg + bracket + number + colon + number + bracket + id + semicolon。"""
        tokens = lexer.tokenize("reg [7:0] data;")
        types = [t.type for t in tokens]
        assert "keyword.reg" in types
        assert "bracket.l_square_bracket" in types
        assert "bracket.r_square_bracket" in types
        assert types[-2] == "id"
        assert types[-1] == "symbol.base.semicolon"

    def test_assign_statement(self, lexer):
        """assign a = b; → 5 tokens。"""
        tokens = lexer.tokenize("assign a = b;")
        types = [t.type for t in tokens]
        assert types == [
            "keyword.assign",
            "id",
            "symbol.base.equal",
            "id",
            "symbol.base.semicolon",
        ]

    def test_line_and_column_numbers(self, lexer):
        """多行输入的 token 行号/列号正确。"""
        tokens = lexer.tokenize("module m;\nwire a;\nendmodule")
        # module: line=1, col=0
        assert tokens[0].line == 1 and tokens[0].column == 0
        # wire: 在第 2 行（前面有 module m; + newline）
        wire_tok = next(t for t in tokens if t.type == "keyword.wire")
        assert wire_tok.line == 2 and wire_tok.column == 0
        # endmodule: line=3, col=0
        end_tok = next(t for t in tokens if t.type == "keyword.endmodule")
        assert end_tok.line == 3 and end_tok.column == 0

    def test_always_block_keywords(self, lexer):
        """always, posedge, negedge 关键字。"""
        tokens = lexer.tokenize("always @(posedge clk)")
        types = [t.type for t in tokens]
        assert "keyword.always" in types
        assert "keyword.posedge" in types

    def test_identifier_underscore(self, lexer):
        """下划线开头标识符。"""
        tokens = lexer.tokenize("_my_signal _123")
        assert len(tokens) == 2
        assert tokens[0].content == "_my_signal"
        assert tokens[1].content == "_123"

    def test_keyword_not_confused_with_identifier(self, lexer):
        """关键字不被误识别为标识符。"""
        tokens = lexer.tokenize("module wire_reg input_output")
        # 这些不是 Verilog 关键字，应为 id
        assert tokens[0].type == "keyword.module"
        # "wire_reg" 整体不是关键字 → id
        # "input_output" 整体不是关键字 → id
        non_keywords = [t for t in tokens if t.type.startswith("keyword")]
        assert len(non_keywords) == 1  # 只有 module


# ═══════════════════════════════════════════════════════
# 注释处理
# ═══════════════════════════════════════════════════════


class TestTokenizeComments:
    """行注释 // 与块注释 /* */ 的正确识别。"""

    def test_line_comment(self, lexer):
        """// 行注释保持为单独 token。"""
        tokens = lexer.tokenize("// this is a comment\na")
        assert tokens[0].type == "comment"
        assert tokens[0].content == "// this is a comment"
        assert tokens[1].type == "newline"
        assert tokens[2].type == "id"

    def test_block_comment(self, lexer):
        """/* */ 块注释。"""
        tokens = lexer.tokenize("/* block comment */")
        assert len(tokens) == 1
        assert tokens[0].type == "comment"
        assert "block comment" in tokens[0].content

    def test_mixed_comments(self, lexer):
        """行注释与块注释混合。"""
        src = "a /* inline */ b // end"
        tokens = lexer.tokenize(src)
        types = [t.type for t in tokens]
        assert "id" in types
        assert "comment" in types

    def test_comment_in_syntax(self, lexer):
        """注释不影响结构化代码的 token 化。"""
        src = "module /* comment */ m; endmodule"
        tokens = lexer.tokenize(src)
        types = [t.type for t in tokens]
        assert "keyword.module" in types
        assert "id" in types
        assert "keyword.endmodule" in types
        assert "comment" in types

    def test_multiline_block_comment(self, lexer):
        """多行块注释。"""
        src = "/* line1\n   line2 */"
        tokens = lexer.tokenize(src)
        assert len(tokens) == 1
        assert tokens[0].type == "comment"
        assert "line1" in tokens[0].content

    def test_empty_block_comment(self, lexer):
        """空块注释 /**/。"""
        tokens = lexer.tokenize("/**/")
        assert len(tokens) == 1
        assert tokens[0].type == "comment"


# ═══════════════════════════════════════════════════════
# 数字字面量
# ═══════════════════════════════════════════════════════


class TestTokenizeNumbers:
    """各种数字格式的正确 token 化。"""

    def test_decimal_integer(self, lexer):
        tokens = lexer.tokenize("42")
        assert tokens[0].type == "literal.number"
        assert tokens[0].content == "42"

    def test_float(self, lexer):
        tokens = lexer.tokenize("3.14")
        assert tokens[0].type == "literal.number"
        assert tokens[0].content == "3.14"

    def test_hex_bit_width(self, lexer):
        """8'hff → 即位宽前缀格式。"""
        tokens = lexer.tokenize("8'hff")
        assert tokens[0].type == "literal.number"
        assert tokens[0].content == "8'hff"

    def test_decimal_bit_width(self, lexer):
        """16'd1000。"""
        tokens = lexer.tokenize("16'd1000")
        assert tokens[0].type == "literal.number"

    def test_binary_bit_width(self, lexer):
        """4'b1010。"""
        tokens = lexer.tokenize("4'b1010")
        assert tokens[0].type == "literal.number"

    def test_signed_literal(self, lexer):
        """16'sd100 — signed 修饰。"""
        tokens = lexer.tokenize("16'sd100")
        assert tokens[0].type == "literal.number"

    def test_multiple_numbers(self, lexer):
        """空格分隔的多个数字各自独立。"""
        tokens = lexer.tokenize("42 3.14 8'hff")
        assert len(tokens) == 3
        for t in tokens:
            assert t.type == "literal.number"


# ═══════════════════════════════════════════════════════
# 字符串字面量
# ═══════════════════════════════════════════════════════


class TestTokenizeStrings:
    """字符串字面量的 token 化。"""

    def test_basic_string(self, lexer):
        tokens = lexer.tokenize('"hello"')
        assert tokens[0].type == "literal.string"
        assert tokens[0].content == '"hello"'

    def test_string_with_spaces(self, lexer):
        tokens = lexer.tokenize('"hello world"')
        assert tokens[0].type == "literal.string"

    def test_string_with_symbols(self, lexer):
        tokens = lexer.tokenize('"path/to/file.v"')
        assert tokens[0].type == "literal.string"


# ═══════════════════════════════════════════════════════
# 边界条件与特殊字符
# ═══════════════════════════════════════════════════════


class TestTokenizeEdgeCases:
    """空输入、纯空白、特殊输入。"""

    def test_empty_input(self, lexer):
        tokens = lexer.tokenize("")
        assert tokens == []

    def test_whitespace_only(self, lexer):
        tokens = lexer.tokenize("   \t  ")
        assert tokens == []

    def test_newline_only(self, lexer):
        """纯换行返回 newline token。"""
        tokens = lexer.tokenize("\n\n")
        assert len(tokens) == 2
        assert tokens[0].type == "newline"
        assert tokens[1].type == "newline"

    def test_just_a_semicolon(self, lexer):
        tokens = lexer.tokenize(";")
        assert len(tokens) == 1
        assert tokens[0].type == "symbol.base.semicolon"

    def test_just_a_comment(self, lexer):
        tokens = lexer.tokenize("// just a comment")
        assert len(tokens) == 1
        assert tokens[0].type == "comment"

    def test_operator_characters(self, lexer):
        """单字符运算符独立为 token。"""
        tokens = lexer.tokenize("+ - * / %")
        types = [t.type for t in tokens]
        assert "symbol.base.add" in types
        assert "symbol.base.sub" in types
        assert "symbol.base.multiple" in types
        assert "symbol.base.div" in types
        assert "symbol.base.mod" in types

    def test_comparison_operators(self, lexer):
        """比较运算符。"""
        tokens = lexer.tokenize("== != < > <=")
        types = [t.type for t in tokens][:5]
        # 多字符运算符可能被识别为 symbol.extend 或其他类型
        assert all(t.startswith("symbol") for t in types)

    def test_bitwise_operators(self, lexer):
        """位运算符 & | ^ ~。"""
        tokens = lexer.tokenize("a & b | c ^ d")
        types = [t.type for t in tokens]
        # 标识符中间穿插运算符
        assert types[0] == "id"
        assert types[2] == "id"
        assert types[4] == "id"
        assert types[6] == "id"


# ═══════════════════════════════════════════════════════
# Token classifier（Pratt 解析器分类函数）
# ═══════════════════════════════════════════════════════


class TestTokenClassifier:
    """Pratt 解析器的 is_operator / is_identifier 分类正确性。"""

    def test_is_operator_available(self, classifier):
        assert callable(classifier.is_operator)

    def test_is_identifier_available(self, classifier):
        assert callable(classifier.is_identifier)

    def test_operator_plus(self, classifier, lexer):
        tok = lexer.tokenize("+")[0]
        assert classifier.is_operator(tok) is True

    def test_operator_minus(self, classifier, lexer):
        tok = lexer.tokenize("-")[0]
        assert classifier.is_operator(tok) is True

    def test_identifier_is_not_operator(self, classifier, lexer):
        tok = lexer.tokenize("my_signal")[0]
        assert classifier.is_operator(tok) is False

    def test_keyword_is_not_operator(self, classifier, lexer):
        tok = lexer.tokenize("module")[0]
        assert classifier.is_operator(tok) is False

    def test_literal_is_not_operator(self, classifier, lexer):
        tok = lexer.tokenize("42")[0]
        assert classifier.is_operator(tok) is False

    def test_left_parenthesis_is_not_operator(self, classifier, lexer):
        tok = lexer.tokenize("(")[0]
        assert classifier.is_operator(tok) is False

    def test_right_parenthesis_is_not_operator(self, classifier, lexer):
        tok = lexer.tokenize(")")[0]
        assert classifier.is_operator(tok) is False


# ═══════════════════════════════════════════════════════
# 负面测试 — 垃圾输入/非法字符的容错行为
# ═══════════════════════════════════════════════════════


class TestNegative:
    """故意喂给 Lexer 无法识别或非法的输入，验证其优雅处理。

    核心检验原则：
    - 绝不对合法代码报错（false positive）
    - 对明确非法的输入（不可见字符）抛 ValueError
    - 对结构不完整但 FSM 可自然终止的输入（未闭合字符串/注释），
        返回已解析的部分而非卡死或抛异常
    """

    # ── 应抛 ValueError 的非法字符 ──

    @pytest.mark.parametrize(
        "src",
        [
            "\u200b",  # zero-width space
            "\x00",  # null byte
            "\x01",  # control char SOH
            "\x1a",  # control char SUB
            "\x7f",  # DEL
        ],
    )
    def test_non_printable_raises_value_error(self, lexer, src):
        """零宽/控制字符在 refine_type 阶段 → ValueError。

        （UTF-8 BOM 已由 [space] bom 配置支持为可忽略字符，不在此列。）
        """
        with pytest.raises(ValueError, match="Unexpected token"):
            lexer.tokenize(src)

    @pytest.mark.parametrize(
        "src",
        [
            "wire a = \\",  # trailing backslash
            "\\",  # bare backslash
        ],
    )
    def test_trailing_backslash_raises_value_error(self, lexer, src):
        """孤立的尾部反斜杠（无法归类到任何 token 类型）→ ValueError。"""
        with pytest.raises(ValueError, match="Unexpected token"):
            lexer.tokenize(src)

    # ── 结构不完整（FSM 可自然终止，不抛异常）──

    @pytest.mark.parametrize(
        "src, expected_type",
        [
            ('"hello', "literal.string"),  # unclosed string
            ('"hello world', "literal.string"),  # unclosed multi-word string
        ],
    )
    def test_unclosed_string_at_eof(self, lexer, src, expected_type):
        """未闭合字符串：while 循环在 EOF 自然退出，产出已收集的内容。"""
        tokens = lexer.tokenize(src)
        assert len(tokens) >= 1
        assert tokens[0].type == expected_type

    def test_unclosed_block_comment_at_eof(self, lexer):
        """未闭合块注释：CommentRunner.run() 中 while pos<len(text) 在 EOF 退出。"""
        tokens = lexer.tokenize("/* unclosed")
        assert len(tokens) >= 1
        assert tokens[0].type == "comment"
        assert "unclosed" in tokens[0].content

    def test_unclosed_block_comment_with_newline(self, lexer):
        """未闭合块注释遇到换行时：line 类型的注释以此为界，block 类型继续。"""
        tokens = lexer.tokenize("/* line1\nwire a;")
        assert len(tokens) >= 1
        assert tokens[0].type == "comment"

    # ── 合法 Verilog 符号不应被误报 ──

    @pytest.mark.parametrize(
        "src, expected_type",
        [
            ("@", "symbol.base.at"),
            ("#", "symbol.base.pound"),
            ("$", "symbol.base.dollar"),
        ],
    )
    def test_valid_verilog_symbols_not_rejected(self, lexer, src, expected_type):
        """@ # $ 是合法 Verilog 符号，不应抛异常。"""
        tokens = lexer.tokenize(src)
        assert len(tokens) == 1
        assert tokens[0].type == expected_type

    # ── 超时安全网（验证 FSM 的 while 循环不会无限跑）──

    @pytest.mark.timeout(2)
    @pytest.mark.parametrize(
        "src",
        [
            "",
            "   ",
            "module m; endmodule",
            "/* unclosed",
            '"hello',
            "!@#$%^&*()",
        ],
    )
    def test_timeout_safety_net(self, lexer, src):
        """安全网：验证所有 FSM while 循环在 2s 内必定终止。"""
        lexer.tokenize(src)


# ═══════════════════════════════════════════════════════
# CRLF / UTF-8 BOM 支持 — 配置驱动，不崩溃
# ═══════════════════════════════════════════════════════


class TestCrlfBomSupport:
    """CRLF 行尾 / UTF-8 BOM 应由 [space] 配置自然支持（lexer 侧修复）。

    修复前 \r 与 \ufeff 无归属 → unrecognized → refine_type 抛 ValueError。
    修复后两者作为可忽略空白吞掉，token 类型序列与 LF / 无 BOM 输入一致。
    """

    def test_crlf_input_tokenizes(self, lexer):
        """CRLF 行尾 → 正常 tokenize，不崩。"""
        src = "module m;\r\n    assign a = b;\r\nendmodule\r\n"
        types = [t.type for t in lexer.tokenize(src)]
        assert types  # 非空
        assert types[0] == "keyword.module"

    def test_crlf_token_types_match_lf(self, lexer):
        """CRLF 与 LF 输入的 token 类型序列应一致（\r 被吞，不产生多余 token）。"""
        lf = lexer.tokenize("module m;\n    assign a = b;\nendmodule\n")
        crlf = lexer.tokenize("module m;\r\n    assign a = b;\r\nendmodule\r\n")
        assert [t.type for t in crlf] == [t.type for t in lf]

    def test_bom_prefix_tokenizes(self, lexer):
        """UTF-8 BOM 文件头 → BOM 被忽略，首个 token 是 module。"""
        src = "\ufeffmodule m;\n    assign a = b;\nendmodule\n"
        tokens = lexer.tokenize(src)
        assert tokens[0].type == "keyword.module"

    def test_bom_prefix_types_match_plain(self, lexer):
        """BOM 前缀与无 BOM 输入的 token 类型序列应一致。"""
        plain = lexer.tokenize("module m;\nendmodule\n")
        bom = lexer.tokenize("\ufeffmodule m;\nendmodule\n")
        assert [t.type for t in bom] == [t.type for t in plain]

    def test_bom_alone_is_ignored(self, lexer):
        """单独 BOM 字符 → 作为空白吞掉，不抛异常。"""
        tokens = lexer.tokenize("\ufeff")
        assert tokens == []


@pytest.fixture(scope="module")
def classifier(config_loaded):
    """加载 Pratt 解析器的 token classifier（需要 parser.token_categories 配置）。"""
    from core.config_registry import ConfigRegistry
    import parser.pratt_parser as pp

    categories = ConfigRegistry._loaded.get("parser.token_categories", {})
    pp.install_token_classifier(categories)
    return pp
