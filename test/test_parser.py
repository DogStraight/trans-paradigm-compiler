from lexer import Lexer
from parser.main_parser import Parser  # 假设你的 Parser 类在 main_parser.py 中
import json


def test_parse():
    source = "a : int = 1 + 2 * 3\n"
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        with open("temp/ast.json", "w") as f:
            json.dump(ast.dump(), f, indent=2)  # indent 可选，让输出更可读

    else:
        print("Parsing failed")


if __name__ == "__main__":
    test_parse()
