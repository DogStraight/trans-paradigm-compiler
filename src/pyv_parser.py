import toml
import os

from pyv_parser_prototype import PyvParserPrototype, GrammarRule


class PyvParser(PyvParserPrototype):
    def __init__(self) -> None:
        super().__init__()
        self.rules_file = None

    def load_rule(self, keywords, productions, node_info) -> GrammarRule:
        return GrammarRule(
            search_keyword=keywords,
            productions=productions, node_info=node_info)

    def add_grammar_rules(self, rules_file: str):
        # validate rules file
        if not os.path.isfile(rules_file):
            raise FileNotFoundError(f"Rules file {rules_file} not found.")
        self.rules_file = rules_file

        # read rules file
        with open(rules_file, "r") as f:
            f_content = f.read()

        # parse rules
        rules = toml.loads(f_content)

        # add rules to parser
        for content in rules.values():
            self.add_grammar_rule(
                self.load_rule(
                    content["keywords"],
                    content["productions"],
                    content["node_info"]))

    def dump_grammar_rules(self) -> None:
        print(self.grammar_rules)
