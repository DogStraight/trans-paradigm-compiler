from lexer import Lexer
from parser import Parser
import json
import os


def test_parse():
    test_cases = [
        {"name": "variable_definition", "source": "a : int = 1 + 2 * 3\n"},
        {
            "name": "arithmetic_precedence",
            "source": "result : float = (1 + 2) * 3 - 4 / 2\n",
        },
        {"name": "comparison", "source": "flag : bool = 5 > 3\n"},
        {"name": "chained_comparison", "source": "check : bool = 1 < 2 and 3 == 3\n"},
        {"name": "parenthesized_expr", "source": "value : int = (2 + 3) * (4 - 1)\n"},
        {"name": "boolean_literal", "source": "ok : bool = True\n"},
        {
            "name": "multiple_variables",
            "source": "x : int = 10\ny : int = 20\nsum : int = x + y\n",
        },
        {"name": "float_literal", "source": "pi : float = 3.1415\n"},
        {"name": "complex_types", "source": "nums : [int]\nmaybe : ?int\n"},
        {"name": "list_literal", "source": "nums : [float] = [1.0, 2.0, 3.0,]\n"},
        {"name": "nested_list", "source": "matrix : [[int]] = [[1, 2], [3, 4]]\n"},
        {"name": "optional_in_list", "source": "opt_list : [?int] = [None, 5]\n"},
        {"name": "id_list", "source": "a b c\n"},
        # 新增测试用例
        {"name": "string_literal", "source": "s : str = \"hello world\"\n"},
        {"name": "string_assign", "source": "msg = \"hello\"\n"},
        {"name": "unary_ops", "source": "neg : int = -5\npos : int = +3\n"},
        {"name": "power_mod", "source": "a : int = 2 ** 8\nb : int = 10 % 3\n"},
        {"name": "function_call", "source": "result = foo(1, 2)\n"},
        {"name": "none_literal", "source": "val : ?int = None\n"},
        {"name": "logic_expression", "source": "flag : bool = True and False or True\n"},
    ]

    # 确保输出目录存在
    os.makedirs("temp", exist_ok=True)

    for case in test_cases:
        print(f"\n--- Testing: {case['name']} ---")
        lexer = Lexer()
        tokens = lexer.tokenize(case["source"])
        parser = Parser()
        ast = parser.parse(tokens)
        if ast:
            output_file = f"temp/ast_{case['name']}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(ast.dump(), f, indent=2)
            print(f"AST saved to {output_file}")
        else:
            print(f"Parsing failed for {case['name']}")


def test_if():
    source = """if x > 0:
    y = 10
else:
    y = -10
"""
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        output_file = f"temp/ast_if.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(ast.dump(), f, indent=2)
        print(f"AST saved to {output_file}")
    else:
        print("Parsing failed for if statement")


def test_while():
    source = """while x > 0:
    y = y - 1
"""
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        output_file = "temp/ast_while.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(ast.dump(), f, indent=2)
        print(f"AST saved to {output_file}")
    else:
        print("Parsing failed for while statement")


def test_for():
    source = """for i in range:
    sum = sum + i
"""
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        output_file = "temp/ast_for.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(ast.dump(), f, indent=2)
        print(f"AST saved to {output_file}")
    else:
        print("Parsing failed for for statement")


def test_import():
    source = """import sys
import numpy as np
from math import pi
from os import path as osp
"""
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        output_file = "temp/ast_import.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(ast.dump(), f, indent=2)
        print(f"AST saved to {output_file}")
    else:
        print("Parsing failed for import statements")


def test_misc():
    source = """pass
break
continue
"""
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    parser = Parser()
    ast = parser.parse(tokens)
    if ast:
        output_file = "temp/ast_misc.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(ast.dump(), f, indent=2)
        print(f"AST saved to {output_file}")
    else:
        print("Parsing failed for misc statements")


def test_all():
    """运行所有测试"""
    test_parse()
    test_if()
    test_while()
    test_for()
    test_import()
    test_misc()


if __name__ == "__main__":
    # 运行全部测试
    test_all()
