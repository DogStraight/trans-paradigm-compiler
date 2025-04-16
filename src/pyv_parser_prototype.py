from abc import ABC, abstractmethod
from copy import deepcopy
from enum import Enum, auto

from pyv_definition import Token, Node, GrammarRule
from pyv_utils import get_close_bracket_string, RecursionGuardManager


class PyvParserPrototype(ABC):
    def __init__(self) -> None:
        self.grammar_rules = []

    def add_grammar_rule(self, rule: GrammarRule) -> None:
        """the grammar rule should contain the search keyword
        and list of production"""
        self.grammar_rules.append(rule)

    @abstractmethod
    def dump_grammar_rules(self) -> None:
        """print the grammar rules"""

    def search_grammar_rule(self, keywords: str) -> list[GrammarRule]:
        """search the grammar rule by the search keyword"""
        match_rules = []
        for rule in self.grammar_rules:
            if keywords in rule.keywords:
                match_rules.append(rule)
        return match_rules

    def read_one_line_code(self, token_generator) -> list[Token]:
        token_list = []
        for token in token_generator:
            if token.type == "newline":
                break
            token_copy = deepcopy(token)
            token_list.append(token_copy)
        return token_list

    @abstractmethod
    def parse(self, token_generator) -> Node:
        """parse the code by the grammar rules"""


class GrammarRuleChecker:
    class ExpressionMatchType(Enum):
        token = auto()
        grammar_rule = auto()
        branch = auto()
        repeated = auto()
        optional = auto()

    def __init__(self, grammar_rules: list[GrammarRule]) -> None:
        self.grammar_rules = grammar_rules
        # self.recursion_guard = RecursionGuardManager()

    def search_grammar_rule_by_name(self, name: str) -> GrammarRule:
        for rule in self.grammar_rules:
            if rule.name == name:
                return rule

        raise ValueError(f"Grammar rule {name} not found")

    def interpret_production_exp(self, exp: str):
        # if the first char of exp is lowercase,
        # means the exp is a type of token
        # return the token type
        if exp[0].islower():
            return self.ExpressionMatchType.token, exp

        # if the first char of exp is uppercase,
        # classification discussion
        # if the exp is a grammar rule, return the grammar rule
        if exp.startswith("GrammarRule"):
            grammar_name = get_close_bracket_string("(", exp)
            rule = self.search_grammar_rule_by_name(grammar_name)
            return self.ExpressionMatchType.grammar_rule, rule

        if exp.startswith("Branch"):
            branch_list = get_close_bracket_string("(", exp).split("|")
            alternate = []
            for branch in branch_list:
                if branch.islower():
                    alternate.append(branch)
                rule = self.search_grammar_rule_by_name(grammar_name)
                alternate.append(rule)
            return self.ExpressionMatchType.branch, alternate

        raise ValueError(f"Invalid production expression: {exp}")

    def fuzzy_matching_grammar(
        self, token_list: list[Token]
    ) -> list[GrammarRule | None]:
        # try to match the production with the token list
        if not token_list:
            return []
        first_token_type = token_list[0].type
        match_rule = []
        for rule in self.grammar_rules:
            for keyword in rule.keywords:
                if first_token_type.lower() in keyword.lower():
                    match_rule.append(rule)
        return match_rule

    def check(self, token_list: list[Token]) -> tuple[bool, GrammarRule | None]:
        match_rules = self.fuzzy_matching_grammar(token_list)
        for rule in match_rules:
            if self.special_grammar_check(token_list, rule):
                return rule.name, True
        return None, False

    def calculate_token_length(self) -> int:
        return 1

    def calculate_grammar_rule_length(self, rule: GrammarRule) -> list[int]:
        return self.fix_grammar_length(rule)

    def calculate_branch_length(self, branches: list) -> list[int]:
        lengths = []
        for branch in branches:
            if isinstance(branch, str):
                lengths.append(1)
            else:
                lengths.extend(self.fix_grammar_length(branch))
        return list(set(lengths))

    def update_lengths(self, current_lengths: list[int], increment) -> list[int]:
        if isinstance(increment, int):
            return [x + increment for x in current_lengths]
        elif isinstance(increment, list):
            new_lengths = []
            for i in increment:
                new_lengths.extend([x + i for x in current_lengths])
            return list(set(new_lengths))
        raise ValueError(f"Invalid increment type: {type(increment)}")

    def fix_grammar_length(self, rule: GrammarRule) -> list[int]:
        lengths = [0]
        for exp in rule.production:
            match_type, match_target = self.interpret_production_exp(exp)
            match match_type:
                case self.ExpressionMatchType.token:
                    increment = self.calculate_token_length()
                case self.ExpressionMatchType.grammar_rule:
                    increment = self.calculate_grammar_rule_length(match_target)
                case self.ExpressionMatchType.branch:
                    increment = self.calculate_branch_length(match_target)
                case _:
                    raise ValueError(f"Unsupported match type: {match_type}")
            lengths = self.update_lengths(lengths, increment)
        return lengths

    def special_grammar_check(self, token_list: list[Token], rule: GrammarRule) -> bool:
        # check is token list empty
        if not token_list:
            raise ValueError("Token list is empty")

        # length check
        if len(token_list) not in self.fix_grammar_length(rule):
            return False

        # check the production exp
        # assert that exp is a token type
        idx = 0
        for exp in rule.production:
            match_type, match_target = self.interpret_production_exp(exp)
            match match_type:
                case self.ExpressionMatchType.token:
                    if token_list[idx].type != match_target:
                        return False
                    idx += 1
                case self.ExpressionMatchType.grammar_rule:
                    for length in self.fix_grammar_length(match_target):
                        assert isinstance(match_target, GrammarRule)
                        if self.special_grammar_check(
                            token_list[idx : idx + length], match_target
                        ):
                            idx += length
                            break
                    else:
                        return False
                case self.ExpressionMatchType.branch:
                    pass
                case _:
                    raise ValueError(f"Unsupported match type: {match_type}")
        return True


if __name__ == "__main__":
    input_str = "a = b?"

    from pyv_utils import load_rule

    test_rule = []
    test_rule.append(
        load_rule(
            "test_rule_assignment",
            {
                "keywords": ["testId"],
                "production": ["id", "symbol.base.equal", "id"],
                "node_info": {},
            },
        )
    )
    test_rule.append(
        load_rule(
            "test_rule_nesting",
            {
                "keywords": ["testIdNest"],
                "production": [
                    "GrammarRule(test_rule_assignment)",
                    "symbol.base.question_mark",
                ],
                "node_info": {},
            },
        )
    )

    from pyv_lexer import PyvLexer
    import copy

    lexer = PyvLexer()
    token_generator = lexer.tokenize(input_str)

    tokens = []
    for token in token_generator:
        token_copy = copy.deepcopy(token)
        tokens.append(token_copy)

    checker = GrammarRuleChecker(test_rule)
    is_match, matched_rule = checker.check(tokens)
    print(is_match)
