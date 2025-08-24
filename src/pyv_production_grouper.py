from pyv_grammar_rules_register import GrammarRulesRegister
from pyv_definition import Token, GrammarRule, GroupedToken
from pyv_grammar_checker import GrammarRuleChecker
from src.checker_src.feature import ExpFeature


class ProductionGrouper:
    """标记token流中属于相同production位置的token"""

    def __init__(
        self,
        checker: GrammarRuleChecker,
        rules: dict[str, GrammarRule] = GrammarRulesRegister().rules_registration(),
    ):
        self.checker = checker
        self.rules = rules

    def group_ip(
        self, ip: tuple[ExpFeature, list], tokens: list[Token], current_idx: int
    ) -> tuple[list[GroupedToken], int]:
        group_tokens = []
        cost_tokens_len = 0
        feature, processed = ip
        match feature:
            case ExpFeature.GrammarCall:
                # 处理语法规则调用(@)
                assert isinstance(processed[0], GrammarRule)
                for production in processed[0].production:
                    ip = self.checker.interpret_rule(production)
                    group_tokens_sub, cost_tokens_len_sub = self.group_ip(
                        ip, tokens, current_idx
                    )
                    group_tokens.extend(group_tokens_sub)
                    cost_tokens_len += cost_tokens_len_sub
                pass
            case ExpFeature.Optional:
                # 处理可选元素([])
                match_rule, is_match = self.checker.check(tokens[current_idx:])
                if is_match is False and match_rule is None:
                    # 没有出现可选元素，跳过可选元素
                    return [], 0
                for optional in processed:
                    if (
                        self.checker.check_production(
                            optional, tokens[current_idx:]
                        )[1]
                        != False
                    ):
                        group_tokens_sub, cost_tokens_len_sub = self.group_ip(
                            ip, tokens, current_idx
                        )
                        group_tokens.extend(group_tokens_sub)
                        cost_tokens_len += cost_tokens_len_sub
            case ExpFeature.Repeat:
                offset: int = 0
                _, cost_len = self.checker.check(tokens[current_idx:])
                # 确认重复模式 ,重复模式由于ip解析器对特征的解释是有限定的(我也不知道为什么)，所以取第一项
                repeat_mode = processed[0]
                rep_group_tokens = []
                while True:
                    if (
                        self.checker.check_production(
                            repeat_mode, tokens[current_idx + offset :]
                        )[1]
                        == False
                    ):
                        break
                    group_tokens_sub, cost_tokens_len_sub = self.group_ip(
                        repeat_mode, tokens, current_idx + offset
                    )
                    offset += cost_tokens_len_sub
                    rep_group_tokens.append(group_tokens_sub)
                cost_tokens_len = offset
                group_tokens.extend(rep_group_tokens)
                pass
            case ExpFeature.Branch:
                for branch in processed:
                    if (
                        self.checker.check_production(branch, tokens[current_idx:])[1]
                        is True
                    ):
                        branch_group_tokens, cost_tokens_len = self.group_ip(
                            branch, tokens, current_idx
                        )
                        group_tokens.extend(branch_group_tokens)
                pass
            case ExpFeature.NoFeature:
                # 处理普通token
                no_feature_token = tokens[current_idx]
                gt = GroupedToken(processed[0], current_idx)
                gt.tokens.append(no_feature_token)
                group_tokens.append(gt)
                cost_tokens_len += 1
                pass
        return group_tokens, cost_tokens_len

    def group(self, tokens: list[Token], match_rule: GrammarRule) -> list[GroupedToken]:
        grouped_tokens = []
        token_idx = 0
        for exp in match_rule.production:
            ip = self.checker.interpret_rule(exp)
            if token_idx > len(tokens):
                raise ValueError("token_idx out of range")
            grouped_ip_tokens, cost_tokens_len = self.group_ip(ip, tokens, token_idx)
            token_idx += cost_tokens_len
            grouped_tokens.append((exp, grouped_ip_tokens))
        return grouped_tokens


def test_case_1():
    checker = GrammarRuleChecker()
    grouper = ProductionGrouper(checker)  # 已经继承了checker的rules
    test_input_str = "a = b + c"
    from pyv_lexer import Lexer

    lexer = Lexer()
    tokens = lexer.return_token_list(test_input_str)
    match_rule, is_match = checker.check(tokens)
    if not is_match:
        raise ValueError("match_rule not found")
    assert match_rule is not None
    grouped_tokens = grouper.group(tokens, match_rule)
    print(grouped_tokens)


if __name__ == "__main__":
    test_case_1()
