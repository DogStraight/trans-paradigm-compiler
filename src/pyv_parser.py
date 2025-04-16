import toml


from pyv_utils import load_rule

from pyv_parser_prototype import (
    PyvParserPrototype,
)


class PyvParser(PyvParserPrototype):
    def __init__(self) -> None:
        super().__init__()
        self.rules_file = None

    def add_grammar_rules(self, rules_file: str):
        self.rules_file = rules_file
        with open(rules_file, "r") as f:
            f_content = f.read()
        rules = toml.loads(f_content)
        for name, rule_content in rules.items():
            self.add_grammar_rule(load_rule(name, rule_content))

    def dump_grammar_rules(self, dump_dir) -> None:
        dump_dict = {}
        for rule in self.grammar_rules:
            dump_dict.update(rule.dump())
            with open(f"{dump_dir}/{rule.name}.toml", "w") as f:
                f.write(toml.dumps(rule.dump()))

        with open(self.rules_file, "w") as f:
            f.write(toml.dumps(dump_dict))

    def parse(self, token_generator):
        return super().parse(token_generator)


if __name__ == "__main__":
    parser = PyvParser()
    parser.add_grammar_rules("grammar/rules.toml")
    parser.dump_grammar_rules("grammar/rule_dump")
