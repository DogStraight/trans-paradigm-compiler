from abc import ABC, abstractmethod
from copy import deepcopy

from pyv_definition import Token, Node, GrammarRule


class PyvParserPrototype(ABC):
    def __init__(self) -> None:
        self.grammar_rules = []

    def add_grammar_rule(self, rule: GrammarRule) -> None:
        """the grammar rule should contain the search keyword
        and list of production"""
        self.grammar_rules.append(rule)

    @abstractmethod
    def dump_grammar_rules(self, dump_dir) -> None:
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
    def parse(self, token_generator) -> Node | None:
        """parse the code by the grammar rules"""
