from lexer import Lexer
from parser.main_parser import Parser  # 假设你的 Parser 类在 main_parser.py 中


def test_parse():
    source = "a : int = 1 + 2 * 3\n"
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    print("Tokens:")
    for token in tokens:
        print(token)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        print("AST dump:")
        print(ast.dump())
    else:
        print("Parsing failed")


if __name__ == "__main__":
    test_parse()
