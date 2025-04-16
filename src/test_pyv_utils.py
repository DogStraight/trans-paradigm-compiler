from copy import deepcopy

from pyv_parser_prototype import GrammarRule
from pyv_lexer import PyvLexer
from pyv_parser import PyvParser


def test_grammar_filter(input_str: str, input_production: list):

    lexer = PyvLexer()
    tokens = lexer.tokenize(input_str)

    token_list = []
    for token in tokens:
        token_copy = deepcopy(token)
        token_list.append(token_copy)

    parser = PyvParser()
    parser.add_grammar_rules("grammar/rules.toml")

    rule = GrammarRule(
        name="test",
        keywords=["test"],
        production=input_production,
        node_info={},
    )
    parser.add_grammar_rule(rule)


if __name__ == "__main__":
    test_grammar_filter(
        "b a c",
        ["Multiple(Variable)"],
    )
