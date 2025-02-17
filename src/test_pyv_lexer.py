from pyv_lexer import PyvLexer


def test_lexer():
    lexer = PyvLexer()
    token_generator = lexer.tokenize('hello')
    for token in token_generator:
        print(token.type, token.content)


if __name__ == "__main__":
    test_lexer()
