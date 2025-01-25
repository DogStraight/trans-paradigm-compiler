from pyv_lexer import PyvLexer


def test_lexer():
    lexer = PyvLexer()
    token_iter = lexer.tokenize("module adder(a, b, c);")
    for token in token_iter:
        print(token.type, token.content)


if __name__ == "__main__":
    test_lexer()
