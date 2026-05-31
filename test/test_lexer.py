from lexer import Lexer
from err import UnexpectedTokenError


def _check_tokens(tokens, expected_types):
    """辅助函数：验证 token 类型列表是否匹配"""
    assert len(tokens) == len(expected_types), (
        f"Token数量不匹配: 实际 {len(tokens)}, 预期 {len(expected_types)}\n"
        f"实际类型: {[t.type for t in tokens]}"
    )
    for i, (token, expected) in enumerate(zip(tokens, expected_types)):
        assert token.type == expected, (
            f"Token {i+1} 类型不匹配: "
            f"实际 '{token.type}', 预期 '{expected}'"
        )


def test_basic_tokens():
    """基础Token识别"""
    lexer = Lexer()
    tokens = lexer.tokenize("a = 123 + 'test'")
    _check_tokens(tokens, [
        "id",
        "symbol.base.equal",
        "literal.number",
        "symbol.base.add",
        "literal.string",
    ])


def test_boundary():
    """边界条件"""
    lexer = Lexer()
    tokens = lexer.tokenize("_var = 1\nx += 2.3")
    _check_tokens(tokens, [
        "id",
        "symbol.base.equal",
        "literal.number",
        "newline",
        "id",
        "symbol.extend.add_equal",
        "literal.number",
    ])


def test_complex_scene():
    """复杂场景（关键字、缩进、括号）"""
    lexer = Lexer()
    tokens = lexer.tokenize("if x > 0:\n    print('hello')")
    _check_tokens(tokens, [
        "keyword.if",
        "id",
        "symbol.base.bigger",
        "literal.number",
        "symbol.base.colon",
        "newline",
        "space.indent",
        "id",
        "bracket.l_parentheses",
        "literal.string",
        "bracket.r_parentheses",
    ])


def test_unrecognized_token():
    """非法字符应抛出 UnexpectedTokenError"""
    lexer = Lexer()
    try:
        lexer.tokenize("a ￥ b")
        assert False, "应当抛出 UnexpectedTokenError 但未抛出"
    except UnexpectedTokenError:
        pass  # 预期异常


def test_all():
    """运行所有 lexer 测试"""
    test_basic_tokens()
    test_boundary()
    test_complex_scene()
    test_unrecognized_token()
    print("所有 lexer 测试通过!")


if __name__ == "__main__":
    test_all()
