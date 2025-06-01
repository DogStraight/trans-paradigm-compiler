import unittest
from pathlib import Path
import toml
import copy

from pyv_lexer import Lexer
from pyv_grammar_checker import GrammarRuleChecker
from pyv_utils import load_rule


class TestGrammarRuleChecker(unittest.TestCase):
    def setUp(self) -> None:
        self.lexer = Lexer()
        rules_file = Path(__file__).parent.parent / "grammar" / "rules.toml"
        self.grammar_checker = GrammarRuleChecker(
            [
                load_rule(name, rule_content)
                for name, rule_content in toml.loads(rules_file.read_text()).items()
            ]
        )

    def test_var_expr(self):
        token_generator = self.lexer.tokenize("x int = 10 + 1")
        tokens = []

        for token in token_generator:
            tokens.append(copy.deepcopy(token))
        rule, is_valid = self.grammar_checker.check(tokens)
        assert rule is not None
        if is_valid:
            print(rule.name, "check pass")
        else:
            print("none of the rules match the input")

    def test_if_statement(self):
        token_generator = self.lexer.tokenize("if (x > 0) { y = 1 } else { y = 0 }")
        tokens = []

        for token in token_generator:
            tokens.append(copy.deepcopy(token))
        if_rule = self.grammar_checker.rules["IfStmt"]
        cost, is_valid = self.grammar_checker.check_specific_rules(if_rule, tokens)
        if is_valid:
            print(f"if stmt grammar check pass")
        else:
            print("if stmt grammar check fail")

    def test_while_loop(self):
        token_generator = self.lexer.tokenize("while (x > 0) { x = x - 1 }")
        tokens = []

        for token in token_generator:
            tokens.append(copy.deepcopy(token))
        rule, is_valid = self.grammar_checker.check(tokens)
        assert rule is not None
        self.assertTrue(is_valid)
        self.assertEqual(rule.name, "WhileStmt")
        if is_valid:
            print(rule.name, "check pass")
        else:
            print("none of the rules match the input")

    def test_code_block(self):
        token_generator = self.lexer.tokenize("{ x = 1; y = 2 }")
        tokens = []

        for token in token_generator:
            tokens.append(copy.deepcopy(token))
        rule, is_valid = self.grammar_checker.check(tokens)
        assert rule is not None
        self.assertTrue(is_valid)
        self.assertEqual(rule.name, "Block")
        if is_valid:
            print(rule.name, "check pass")
        else:
            print("none of the rules match the input")


if __name__ == "__main__":
    unittest.main()
