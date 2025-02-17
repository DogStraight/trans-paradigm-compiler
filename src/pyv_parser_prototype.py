from abc import ABC, abstractmethod
from copy import deepcopy


class Node:
    def __init__(self) -> None:
        pass

    def dump(self) -> dict:
        dump_dict = {}
        for attr, value in self.__dict__.items():
            dump_dict[attr] = value.dump() if isinstance(
                value, Node) else value
        return {self.name: dump_dict}


def validate_string_list(items, list_name):
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{list_name} should be a string")


class GrammarRule:
    def __init__(
        self,
        search_keyword: list[str],
        productions: list[str],
        node_info: list[str]
    ) -> None:
        validate_string_list(search_keyword, "search_keyword")
        validate_string_list(productions, "productions")
        validate_string_list(node_info, "node_info")
        self.search_keyword = search_keyword
        self.productions = productions
        self.node_info = node_info
        pass


class PyvParserPrototype(ABC):
    def __init__(self) -> None:
        self.grammar_rules = []
        pass

    def add_grammar_rule(self, rule: GrammarRule) -> None:
        """ the grammar rule should contain the search keyword
        and list of productions """
        self.grammar_rules.append(rule)
        pass

    @abstractmethod
    def dump_grammar_rules(self) -> None:
        """ print the grammar rules """
        pass

    @abstractmethod
    def search_grammar_rule(self, search_keyword: str) -> list[GrammarRule]:
        """ search the grammar rule by the search keyword """
        pass

    def read_one_line_code(self, token_generator) -> list[str]:
        token_list = []
        for token in token_generator:
            token_copy = deepcopy(token)
            token_list.append(token_copy)
            if token.type == "newline":
                break
        return token_list

    def read_one_block_code(self, token_generator) -> list[str]:
        """ this function is only used at the beginning of the code block """
        # assume that the first token is the indention token
        indent_deep = token_generator.indent_deep
        token_list = []
        while True:
            token_list += self.read_one_line_code(token_generator)
            indention_token = next(token_generator)
            if indention_token.type == "dedent" \
                    and token_generator.indent_deep <= indent_deep:
                break

    def parse_code_by_grammar_rules(self, token_generator) -> Node:
        """ parse the code by the grammar rules """
        pass