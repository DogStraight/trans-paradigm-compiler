import toml
from pyv_definition import GrammarRule, FileManager


class GrammarRulesRegister:
    def __init__(self):
        self.rules = {}

    def rules_registration(self) -> dict[str, GrammarRule]:
        rules_dict = FileManager.load_rules()
        for rule_name, rule_dict in rules_dict.items():
            rule: GrammarRule = GrammarRule(
                rule_name, rule_dict["production"], rule_dict["node"]
            )
            self.rules[rule_name] = rule
        return self.rules
