from lexer import Lexer
from parser.main_parser import Parser
import json
import os

def test_parse():
    test_cases = [
        {
            "name": "variable_definition",
            "source": "a : int = 1 + 2 * 3\n"
        },
        {
            "name": "arithmetic_precedence",
            "source": "result : float = (1 + 2) * 3 - 4 / 2\n"
        },
        {
            "name": "comparison",
            "source": "flag : bool = 5 > 3\n"
        },
        {
            "name": "chained_comparison",
            "source": "check : bool = 1 < 2 and 3 == 3\n"
            # 注意：当前规则中没有 and/or 支持，这个测试可能会失败，需要扩展规则
        },
        {
            "name": "parenthesized_expr",
            "source": "value : int = (2 + 3) * (4 - 1)\n"
        },
        {
            "name": "boolean_literal",
            "source": "ok : bool = True\n"
        },
        {
            "name": "multiple_variables",
            "source": "x : int = 10\ny : int = 20\nsum : int = x + y\n"
        }
    ]

    # 确保输出目录存在
    os.makedirs("temp", exist_ok=True)

    for case in test_cases:
        print(f"\n--- Testing: {case['name']} ---")
        lexer = Lexer()
        tokens = lexer.tokenize(case['source'])
        parser = Parser()
        ast = parser.parse(tokens)
        if ast:
            output_file = f"temp/ast_{case['name']}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(ast.dump(), f, indent=2)
            print(f"AST saved to {output_file}")
        else:
            print(f"Parsing failed for {case['name']}")

if __name__ == "__main__":
    test_parse()