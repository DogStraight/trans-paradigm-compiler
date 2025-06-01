import toml
from pathlib import Path

from pyv_definition import Token, GrammarRule
from pyv_utils import get_close_bracket_string
from pyv_err import GrammarRuleNoFoundError
from src.checker_src.feature import ExpFeature, get_exp_features


class GrammarRuleChecker:

    def __init__(self, grammar_rules: list[GrammarRule]) -> None:
        self.rules = {rule.name: rule for rule in grammar_rules}
        self.lookup_path = (
            Path(__file__).parent.parent / "grammar" / "production_lookup.toml"
        )
        self.lookup_table = self._load_lookup_table()

    def _load_lookup_table(self):
        return toml.load(self.lookup_path)

    def _dump_lookup_table(self):
        with open(self.lookup_path, "w") as f:
            toml.dump(self.lookup_table, f)

    def interpret_rule(self, exp: str) -> tuple[ExpFeature, list]:
        assert exp is not None
        feature = get_exp_features(exp)
        processed = []
        match feature:
            case ExpFeature.Branch:
                processed = [self.interpret_rule(b) for b in exp.split("|")]
            case ExpFeature.Optional:
                processed = [self.interpret_rule(get_close_bracket_string("[", exp))]
            case ExpFeature.Repeat:
                processed = [self.interpret_rule(get_close_bracket_string("{", exp))]
            case ExpFeature.GrammarCall:
                grammar_exp = exp.replace("@", "")
                grammar_feature = get_exp_features(grammar_exp)
                if grammar_feature == ExpFeature.NoFeature:
                    grammar_name = grammar_exp
                    if grammar_name not in self.rules:
                        raise GrammarRuleNoFoundError(
                            f"Grammar rule {grammar_name} not found"
                        )
                    processed = [self.rules[grammar_name]]
                elif grammar_feature == ExpFeature.Branch:
                    processed = [self.interpret_rule(b) for b in exp.split("|")]
                    feature = ExpFeature.Branch
            case _:
                processed = [exp]
        return feature, processed

    def check(self, tokens: list[Token]) -> tuple[GrammarRule | None, bool]:
        assert tokens is not None
        if not tokens:
            return None, False

        tokens.append(Token(type="EOG"))  # add end of grammar token

        if not isinstance(tokens[0], Token):
            raise TypeError(f"Expected Token type, got {type(tokens[0]).__name__}")

        first_token = tokens[0]
        if first_token.type in self.lookup_table:
            match_rules = self.lookup_table[first_token.type]
            for rule_name in match_rules:
                rule = self.rules.get(rule_name)
                if isinstance(rule, GrammarRule):
                    cost, matched = self.check_specific_rules(rule, tokens)
                else:
                    raise TypeError(
                        f"Expected GrammarRule type, got {type(rule).__name__}"
                    )
                if matched and tokens[cost].type == "EOG":
                    return rule, True

        # Fallback to checking all rules if no match found
        for rule in self.rules.values():
            cost, matched = self.check_specific_rules(rule, tokens)
            if matched and tokens[cost].type == "EOG":
                # there have two cases
                # 1. the type is added to the lookup table,
                # but the rule is not added to the lookup table
                if first_token.type not in self.lookup_table:
                    self.lookup_table[first_token.type] = [rule.name]
                # 2. the type is not added to the lookup table
                if rule.name not in self.lookup_table[first_token.type]:
                    self.lookup_table[first_token.type] += [rule.name]
                self._dump_lookup_table()
                return rule, True

        return None, False

    def check_specific_rules(
        self, rule: GrammarRule, tokens: list[Token]
    ) -> tuple[int, bool]:
        assert rule is not None
        assert tokens is not None
        ip_list = []
        total_len = 0
        for ip in rule.production:
            ip_list.append(self.interpret_rule(ip))
        for ip in ip_list:
            take_len, is_success = self.check_production(ip, tokens)
            if not is_success:
                return 0, False
            tokens = tokens[take_len:]
            total_len += take_len
        return total_len, True

    def check_production(
        self, ip: tuple[ExpFeature, list], tokens: list[Token]
    ) -> tuple[int, bool]:
        assert ip is not None
        assert tokens is not None
        feature, exp = ip
        match feature:
            case ExpFeature.NoFeature:
                if isinstance(exp[0], str):
                    if exp[0] == tokens[0].type:
                        return 1, True
                return 0, False
            case ExpFeature.Branch:
                for e in exp:
                    take_len, is_success = self.check_production(e, tokens)
                    if is_success:
                        return take_len, True
                return 0, False
            case ExpFeature.Optional:
                take_len, is_success = self.check_production(exp[0], tokens)
                if is_success:
                    return take_len, True
                else:
                    return 0, True
            case ExpFeature.Repeat:
                take_len = 0
                cost_len = 0
                while True:
                    take_len, is_success = self.check_production(
                        exp[0], tokens[cost_len:]
                    )
                    if not is_success:
                        break
                    cost_len += take_len
                return cost_len, True if cost_len > 0 else False
            case ExpFeature.GrammarCall:
                return self.check_specific_rules(exp[0], tokens)
            case _:
                raise NotImplementedError(f"Feature {feature} not implemented")
        pass


if __name__ == "__main__":
    assignment_1 = GrammarRule(
        name="assignment",
        production=["id", "symbol.base.equal"],
        node={},
    )

    assignment_2 = GrammarRule(
        name="assignment_1",
        production=["@assignment", "literal.number", "symbol.base.semicolon"],
        node={},
    )

    assignment_3 = GrammarRule(
        name="assignment_2",
        production=[
            "@assignment",
            "id",
            "symbol.base.semicolon|symbol.base.comma",
            "{symbol.base.question_mark}",
        ],
        node={},
    )
    checker = GrammarRuleChecker([assignment_1, assignment_2, assignment_3])
    checker.lookup_path = (
        Path(__file__).parent.parent / "grammar" / "test_production_lookup.toml"
    )
    target_tokens = [
        Token(content="a", type="id"),
        Token(content="=", type="symbol.base.equal"),
        # Token(content="b", type="id"),
        Token(content="1", type="literal.number"),
        Token(content=";", type="symbol.base.semicolon"),
        # Token(content=",", type="symbol.base.comma"),
        # Token(content="?", type="symbol.base.question_mark"),
        # Token(content="?", type="symbol.base.question_mark"),
        # Token(content="?", type="symbol.base.question_mark"),
    ]
    rule, matched = checker.check(target_tokens)
    print(rule.name if type(rule) == GrammarRule else None, matched)
    pass
