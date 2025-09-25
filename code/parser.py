from define import Node, GrammarRule, GrammarRulesRegister


class PyvParser:
    def __init__(self) -> None:
        self.grammar_rules = GrammarRulesRegister().rules_registration()
        self.root_node = Node("root", body=[])

        # parser state
        # 5 states: normal, check_branch, check_repeat, check_optional,grammar_call
        self.parser_states = [
            "normal",
            "check_branch",
            "check_repeat",
            "check_optional",
            "grammar_call",
        ]
        self.parser_current_state = "normal"
        self.current_node = self.root_node
        self.current_token = None

        # node level stack
        # if a node is update, push it into stack, and pop it when it's end case
        self.node_stack = []

    def parse(self, token_generator, parse_text: str) -> Node | None:
        """Parse tokens into AST nodes using grammar rules"""
        tokens = token_generator.return_token_list(parse_text)

        if not tokens:
            print("no tokens input")
            return None

        if not self.grammar_rules:
            print("no grammar rules loaded")
            return None

    def create_node(self, rule: GrammarRule, grouped_token) -> Node | None:
        pass


if __name__ == "__main__":
    pass
