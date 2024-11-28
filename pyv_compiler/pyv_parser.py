from typing import Generator
from os import walk
import toml

from .pyv_lexer import Token, Lexer, _read_token_define, _lex_input
from .pyv_ast_node import \
    Node, RootNode, ClassDefNode, PortListNode, \
    TagNode, \
    InterfaceNode, ExpressionNode, AttributeNode, CallableNode, \
    IfNode


def get_types() -> list[str]:
    _, types, _ = next(walk("./grammar/type"))
    return types


def get_op_precedence() -> dict:
    with open("./grammar/operator_precedence.toml", "r") as _f:
        file_content = _f.read()
    return toml.loads(file_content)


def get_type_info(type_name: str) -> dict:
    with open(f"./grammar/type/{type_name}/type_{type_name}_info.toml", "r")\
            as _f:
        file_content = _f.read()
    return toml.loads(file_content)


def get_close_bracket_string(
        start_bracket: str,
        target_string: str) -> str:
    close_bracket = ""
    close_bracket_dict = {
        "(": ")",
        "[": "]",
        "{": "}",
        "<": ">"
    }
    if start_bracket not in close_bracket_dict:
        print(f"Invalid start bracket: {start_bracket}")
        exit(1)
    close_bracket = close_bracket_dict[start_bracket]
    start: bool = False
    l_bracket_cnt: int = 0
    r_bracket_cnt: int = 0
    extract_string: str = ""
    for ch in target_string:
        if ch == start_bracket:
            start = True
            l_bracket_cnt += 1
        elif ch == close_bracket:
            r_bracket_cnt += 1
        if start is True:
            extract_string += ch
        if start is True and l_bracket_cnt == r_bracket_cnt:
            break
    if l_bracket_cnt != r_bracket_cnt:
        print(f"Invalid bracket pair: {target_string}")
        exit(1)
    return extract_string


class Parser:
    ####################################
    # init method
    ####################################
    def __init__(self, token_input: Generator) -> None:
        self.token_input: Generator = token_input
        self.ast: RootNode = RootNode()
        self.node_level: list[Node] = [self.ast]
        self.current_node: Node = self.ast

        # peek flag
        self.has_peeked: bool = False
        self.peek_token = None
        self.current_token = None
        pass

    ####################################
    # alias for self operation
    ####################################

    def _node_level_step_down(self) -> None:
        self.node_level.pop()
        self.current_node = self.node_level[-1]

    def _node_level_step_up(self, node) -> None:
        self.current_node.add_node(node)
        self.node_level.append(node)
        self.current_node = node

    ####################################
    # parser state machine related method
    ####################################

    def advance(self) -> Token:
        if self.has_peeked:
            self.has_peeked = False
            self.current_token = self.peek_token
            return self.current_token
        self.current_token = next(self.token_input)
        return self.current_token

    def peek(self) -> Token:
        if not self.has_peeked:
            self.has_peeked = True
            return next(self.token_input)
        return self.current_token

    def consume(self, token: Token) -> None:
        if "keyword" in token.type:
            parse_method = getattr(self, f"_parse_{token.content}")
            parse_method()
        elif "id" in token.type:
            pass
        else:
            self.advance()
        pass

    ####################################
    # keyword related method
    ####################################

    def _parse_class(self) -> None:
        node = ClassDefNode()
        self._node_level_step_up(node)
        class_name_token = self.advance()
        if "id" not in class_name_token.type:
            raise Exception(f"Invalid class name: {class_name_token.content}")
        node.set_class_name(class_name_token.content)
        pass

    # port list
    def _parse_input(self) -> None:
        pass

    def _parse_output(self) -> None:
        pass

    def _parse_inout(self) -> None:
        pass

    ####################################
    # main method for parser
    ####################################

    def parse(self, token_input: Generator[Token, None, None]) -> None:
        for token in token_input:
            self.consume(token)
        pass

    def dump_ast(self) -> dict:
        return self.ast.dump()


# this is for test only
if __name__ == "__main__":
    # load token define from file
    token_define = _read_token_define("grammar/token.toml")
    # instance lexer
    pyv_lexer = Lexer(token_define)
    # instance parser
    pyv_parser = Parser(token_define)

    with open("./grammar/module_define.pyv", "r") as f:
        parse_input_raw = f.read()
    parse_input: Generator = _lex_input(
        pyv_lexer, input_str=parse_input_raw)

    pyv_parser.parse(parse_input)

    import json
    dump_ast_json_form = json.dumps(pyv_parser.ast.dump(), indent=4)

    output = open("./output/test_ast.json", "w")
    print(dump_ast_json_form, file=output)
    output.close()
