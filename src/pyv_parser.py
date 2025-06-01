import toml

from pyv_definition import Node
from pyv_grammar_checker import GrammarRuleChecker
from pyv_utils import load_rule
from pyv_parser_prototype import PyvParserPrototype


class PyvParser(PyvParserPrototype):
    def __init__(self, rules_file: str = "") -> None:
        super().__init__()
        self.rules_file = rules_file
        self.checker = None
        if rules_file:
            self._load_grammar_rules()

    def _load_grammar_rules(self):
        """Internal method to load grammar rules"""
        if not self.rules_file:
            return

        self.grammar_rules.clear()
        with open(self.rules_file, "r") as f:
            rules = toml.loads(f.read())
        for name, rule_content in rules.items():
            self.add_grammar_rule(load_rule(name, rule_content))
        self.checker = GrammarRuleChecker(self.grammar_rules)

    def reload_grammar_rules(self, new_rules_file: str = "") -> None:
        """Reload grammar rules from current or new file"""
        if new_rules_file != "":
            self.rules_file = new_rules_file
        self._load_grammar_rules()

    def dump_grammar_rules(self, dump_dir) -> None:
        """Dump current grammar rules to files"""
        if not self.rules_file:
            return

        dump_dict = {}
        for rule in self.grammar_rules:
            dump_dict.update(rule.dump())
            with open(f"{dump_dir}/{rule.name}.toml", "w") as f:
                f.write(toml.dumps(rule.dump()))

        with open(self.rules_file, "w") as f:
            f.write(toml.dumps(dump_dict))

    def parse(self, token_generator):
        """Parse tokens into AST nodes using grammar rules"""
        tokens = list(token_generator)
        if not tokens or not self.checker:
            return None

        rule, matched = self.checker.check(tokens)
        if matched:
            return self._create_node(rule, tokens)
        return None

    def _create_node(self, rule, tokens):
        """Create AST node from matched rule and tokens"""
        node_attrs = {}
        for attr, value_ref in rule.node.items():
            if isinstance(value_ref, str) and value_ref.startswith("$"):
                idx = int(value_ref[1:]) - 1
                if idx < len(tokens):
                    node_attrs[attr] = tokens[idx].content
        return Node(rule.name, **node_attrs)


if __name__ == "__main__":
    parser = PyvParser("grammar/rules.toml")
    parser.dump_grammar_rules("grammar/rule_dump")
