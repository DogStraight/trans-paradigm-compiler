import toml
from pyv_parser import Parser
from pyv_lexer import Lexer

exp = "1"

with open("grammar/token.toml", "r") as f:
    token_define = toml.load(f)

lexer = Lexer(token_define)
parser = Parser(token_define)


if __name__ == "__main__":
    tokens = lexer.tokenize(exp)
    for token in tokens:
        print(token.content, token.type)
    exp_node = parser._eval_expression(exp)
    import json
    with open("exp_node.json", "w") as f:
        print(json.dumps(exp_node.dump(), indent=2), file=f)
