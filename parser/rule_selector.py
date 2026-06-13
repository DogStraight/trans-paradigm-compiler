# parser/rule_selector.py
from typing import List, Dict, Optional
from core.define import Token, GrammarRule
from parser.feature_analyze import analyze_production_features


class RuleSelector:
    def __init__(
        self, grammar_rules: Dict[str, GrammarRule], statement_rule_names: List[str]
    ):
        self.grammar_rules = grammar_rules
        self.statement_rule_names = statement_rule_names

    def get_candidate_rules(self, token: Token) -> List[GrammarRule]:
        # 建立类型到处理函数的映射
        handlers = {}

        # token 处理
        def handle_token(node: dict, visited: set) -> bool:
            return node["token_type"] == token.type

        handlers["token"] = handle_token

        # call 处理
        def handle_call(node: dict, visited: set) -> bool:
            rule_name = node["name"]
            if rule_name in visited or rule_name not in self.grammar_rules:
                return False
            visited.add(rule_name)
            rule = self.grammar_rules[rule_name]
            for prod in rule.production:
                prod_node = analyze_production_features(prod)
                if prod_node and can_start(prod_node, visited.copy()):
                    return True
            return False

        handlers["call"] = handle_call

        # seq 处理
        def handle_seq(node: dict, visited: set) -> bool:
            items = node.get("items", [])
            return bool(items and can_start(items[0], visited))

        handlers["seq"] = handle_seq

        # choice 处理
        def handle_choice(node: dict, visited: set) -> bool:
            return any(can_start(alt, visited) for alt in node.get("alternatives", []))

        handlers["choice"] = handle_choice

        # repeat, optional, plus 共享同一处理逻辑
        def handle_repeat_like(node: dict, visited: set) -> bool:
            elem = node.get("elem")
            return elem is not None and can_start(elem, visited)

        for typ in ("repeat", "optional", "plus"):
            handlers[typ] = handle_repeat_like

        # 递归匹配函数
        def can_start(node: dict, visited: set) -> bool:
            typ = node.get("type")
            handler = handlers.get(typ)
            if handler is None:
                return False
            return handler(node, visited)

        # 收集可能匹配的规则：只检查每个规则的第一条产生式
        possible_rules = []
        for rule in self.grammar_rules.values():
            if not rule.production:
                continue
            first_prod = rule.production[0]
            try:
                features = analyze_production_features(first_prod)
            except Exception:
                continue
            if features and can_start(features, set()):
                possible_rules.append(rule)

        # 按 statement_rule_names 顺序排序
        rule_map = {
            getattr(rule, "name", getattr(rule, "rule_name", None)): rule
            for rule in possible_rules
        }
        ordered = [
            rule_map[name] for name in self.statement_rule_names if name in rule_map
        ]
        return ordered

    def get_block_rule(self, start_token: str) -> Optional[str]:
        for rule_name, rule in self.grammar_rules.items():
            if getattr(rule, "block_start", None) == start_token:
                return rule_name
        return None


if __name__ == "__main__":
    from define import GrammarRulesRegister

    rules_dict = (
        GrammarRulesRegister().rules_registration()
    )  # 得到 Dict[str, GrammarRule]
    s = RuleSelector(rules_dict, [])
    print(s.get_block_rule(""))  # 应该输出 "Root"
    print(s.get_block_rule("space.indent"))  # 应该输出 "Block"
