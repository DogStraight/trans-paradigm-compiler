from typing import Generator
from os import walk
import copy
import re
import toml
import logging


from pyv_lexer import Token, Lexer, _read_token_define, _lex_input
from pyv_ast_node import Node, RootNode, ClassDefNode, PortListNode, TagNode, \
    InterfaceNode, ExpressionNode


logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s')


def get_types() -> list[str]:
    _, types, _ = next(walk("./grammar/type"))
    return types


def get_op_precedence() -> dict:
    with open("./grammar/operator_precedence.toml", "r") as f:
        file_content = f.read()
    return toml.loads(file_content)


def get_type_info(type_name: str) -> dict:
    with open(f"./grammar/type/{type_name}/type_{type_name}_info.toml", "r")\
            as f:
        file_content = f.read()
    return toml.loads(file_content)


def get_log_message() -> dict:
    with open("./log/log_message.toml", "r") as f:
        file_content = f.read()
    log_message = toml.loads(file_content)
    return log_message


def get_close_bracket_string(
        current_token: Token,
        target_string: str) -> str:
    start_bracket = current_token.content
    match start_bracket:
        case "(":
            close_bracket = ")"
        case "[":
            close_bracket = "]"
        case "{":
            close_bracket = "}"
        case "<":
            close_bracket = ">"
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
        message = get_log_message()["parser"]["no_match_bracket"].format(
            line=current_token.start.line,
            column=current_token.start.column)
        logging.error(message)
        exit(1)
    return extract_string


def get_type_param(
        type_name: str,
        current_token: Token,
        param_default_value: list,
        token_input: Generator) -> dict:
    """ there are two option part of type parameter
        one for type parameter input one for default value input"""

    type_info: dict = get_type_info(type_name)
    target_string: str = ""
    for token in token_input:
        target_string += token.content
        if token.type == "newline":
            break

    # check if there is param
    is_current_type_has_param: bool = True
    if "param_list" not in type_info:
        is_current_type_has_param = False
    """ if type has param input , the format like
        'name: type(params,) = default_value' ,we start from the 'type'
        so the rest of string is (params,) = default_value
        if there is no param input the string will be like
        '= default_value' """
    if not re.compile(r"^ *\(").search(target_string):
        is_current_type_has_param = False

    # assign param input
    param_input = {}
    if is_current_type_has_param is True:
        extract_string: str = get_close_bracket_string(
            "(", target_string)
    margin_string = target_string.replace(extract_string, "")
    extract_string = extract_string.replace(" ", "")
    items = extract_string[1:-1].split(",")
    is_dict_input: bool = False
    try:
        if "=" in items[0]:
            is_dict_input = True
    except IndexError:
        message = get_log_message()["parser"]["no_param_input"].format(
            type=type_name,
            line=current_token.start.line,
            column=current_token.start.column)
        logging.error(message)
        exit(1)
    # init idx for separate param and default value
    idx = 0
    for item in items:
        if is_dict_input is True:
            param_name, param_value = item.split("=")
            if param_name in type_info["param_list"]:
                param_input[param_name] = param_value
        else:
            param_default_value[idx] = item
        idx += 1  # max at items number
    # reset idx
    idx = 0
    if is_dict_input is False:
        for p in type_info["param_list"]:
            param_input[p] = param_default_value[idx]
            idx += 1  # max at param_list number

    # check if there is default value input
    is_current_type_has_default: bool = True
    if not re.compile(r"^ *\=").search(margin_string):
        is_current_type_has_default = False
    if type_info["is_accept_default_value"] is False:
        is_current_type_has_default = False

    # assign default value
    if_default_value = []
    if is_current_type_has_default is True:
        margin_string = margin_string.replace(" ", "")[1:]
        items = margin_string.split(",")
        for item in items:
            if_default_value.append()

    return {"param": param_input, "default": if_default_value}


def get_tag_content(token_input: Generator) -> list:
    target_string: list = []
    for token in token_input:
        if token.type == "literal.string":
            target_string.append(token.content)
        if token.type == "bracket.r_parentheses":
            break
    next(token_input)  # skip bracket.r_parentheses
    return target_string


class Parser:
    ####################################
    # magic method
    ####################################
    def __init__(self, token_define: dict) -> None:
        self.locals = {}
        self.token_define = token_define
        self.types = get_types()
        self.log_message = get_log_message()
        self.ast: RootNode = RootNode()

        # node level
        self.node_level: list[Node] = [self.ast]
        self.current_node = self.node_level[-1]
        self.location = "root"
        self.lexer_iter: Generator[Token, None, None] | None = None

        # temp port
        self.current_port: dict = {
            "port_name": "",
            "port_type": "",
            "port_param": {},
            "port_default_value": ""
        }
        pass

    ####################################
    # inner eval method
    ####################################

    def _eval_expression(
            self,
            expression: str) -> ExpressionNode:
        lexer = Lexer(self.token_define)
        # remove space
        expression = expression.replace(" ", "")
        # remove double not
        expression = expression.replace("!!", "")
        tokens = lexer.tokenize(expression)
        node: ExpressionNode = ExpressionNode()
        token_set = []
        op_precedence: dict = get_op_precedence()
        exp_idx = 0
        for token in tokens:
            token_copy = copy.deepcopy(token)
            if "symbol" in token_copy.type:
                token_set.append((
                    token_copy,
                    op_precedence[token_copy.type.split(".")[-1]]))
                exp_idx += len(token_copy.content)
            elif "literal" in token_copy.type or \
                    "id" in token_copy.type:
                token_set.append((token_copy, 0))
                exp_idx += len(token_copy.content)
            elif "bracket.l" in token_copy.type:
                sub_exp = get_close_bracket_string(
                    token_copy, expression[exp_idx:])
                sub_exp_node = self._eval_expression(
                    sub_exp[1:-1])
                token_set.append((sub_exp_node, 0))
                exp_idx += len(sub_exp)
                # skip current token
                sub_tokens = lexer.tokenize(sub_exp[1:])
                # skip bracket content
                for _ in sub_tokens:
                    next(tokens)

        # build expression tree
        token_set_copy: list = []
        is_load_element: bool = False
        is_combine_element: bool = False
        while len(token_set) > 1:
            max_precedence = max([x[1] for x in token_set])
            is_combine_element = False
            for idx, element in enumerate(token_set):
                if element[1] == max_precedence \
                        and is_combine_element is False:
                    new_node: ExpressionNode = ExpressionNode()
                    new_node.add_operator(element[0])
                    if (element[0].type != "symbol.base.logic_not" or
                            element[0].content != "symbol.base.not") and \
                            idx > 0:
                        new_node.add_left_operand(token_set[idx-1][0])
                        token_set_copy.pop()
                    if idx + 1 < len(token_set):
                        new_node.add_right_operand(token_set[idx+1][0])
                    token_set_copy.append((new_node, 0))
                    is_load_element = True
                    is_combine_element = True
                    continue
                else:
                    token_set_copy.append(element)
                    if is_load_element is True:
                        is_load_element = False
                        token_set_copy.pop()
            token_set = token_set_copy
            token_set_copy = []

        # add last node to ast
        if isinstance(token_set[0][0], Token):
            node.add_left_operand(token_set[0][0])
        else:
            node = token_set[0][0]
        return node

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
    # process method for each token type
    ####################################

    def _keyword_process_method(
        self,
        current_token: Token
    ) -> None:
        key_word_type = current_token.type.split(".")[1]
        match key_word_type:
            case "class":
                node: ClassDefNode = ClassDefNode()
                node.update_class_name = True
            case "input" | "output" | "inout":
                node: PortListNode = PortListNode(key_word_type)
            case "interface":
                node: InterfaceNode = InterfaceNode()
            case "tag":
                node: TagNode = TagNode()
                pass
        self._node_level_step_up(node)
    pass

    def _id_process_method(
        self,
        current_token: Token
    ) -> None:
        match self.location:
            case "class_define":
                if self.current_node.update_class_name is True:
                    self.current_node.class_name = current_token.content
                elif self.current_node.update_bases is True:
                    self.current_node.bases_list.append(current_token.content)
                pass

            case "port_list_input" | "port_list_output" | "port_list_inout":
                # decide id is name or type
                if self.current_node.update_port_name is True:
                    self.current_node.update_port_name = False
                    self.current_node.update_port_type = True
                    self.current_port["port_name"] = current_token.content

                elif self.current_node.update_port_type is True:
                    self.current_node.update_port_type = False
                    if current_token.content in self.types:
                        self.current_node.update_port_type = False
                        self.current_port["port_type"] = current_token.content
                    else:
                        log_message =\
                            self.log_message["parser"]["unknown_type"].format(
                                type=current_token.content,
                                line=current_token.start.line,
                                column=current_token.start.column)
                        logging.error(log_message)
                        exit(1)
                    # update port parameter
                    """ if there is no param input use default value """
                    type_info: dict = get_type_info(
                        self.current_port["port_type"])
                    # get type param
                    type_param: list[str] = \
                        list(type_info["param_list"].keys())
                    param_init_value: list[str] = []
                    for p in type_info["param_list"]:
                        param_init_value.append(
                            type_info["param_list"][p]["default"])
                    # init current port
                    self.current_port["port_param"] = {
                        n: v for n, v in zip(type_param, param_init_value)
                    }
                    logging.debug(
                        f"PORT_PARAM:{self.current_port['port_param']}")
                    # get type param input
                    type_param_input = get_type_param(
                        self.current_port["port_type"],
                        current_token,
                        param_init_value,
                        token_input=self.lexer_iter)
                    self.current_node.update_port_name = True
                    logging.debug(
                        f"TYPE_PARAM_INPUT:{type_param_input}")
                    # update port parameter
                    for p in type_param_input["param"]:
                        self.current_port["port_param"][p] \
                            = type_param_input["param"][p]
                    logging.debug(
                        f"PORT_PARAM:{self.current_port['port_param']}")
                    # update port to port list
                    port_copy = copy.deepcopy(self.current_port)
                    if "input" in self.location:
                        del port_copy["port_default_value"]
                    self.current_node.add_port(port_copy)
                pass

            case "interface":
                if current_token.content in self.types \
                        and self.current_node.update_if_name is True:
                    self.current_node.if_name = current_token.content
                    self.current_node.update_if_name = False

                elif self.current_node.update_if_name is True:
                    self.current_node.if_name = current_token.content

                elif self.current_node.update_if_param is True:
                    pass
    pass

    def _space_process_method(
        self,
        current_token: Token
    ) -> None:
        space_type: str = current_token.type.split(".")[-1]
        match space_type:
            case "dedent":
                self._node_level_step_down()
                pass
        pass

    def _bracket_process_method(
        self,
        current_token: Token
    ) -> None:
        match current_token.content:
            case "(":
                match self.location:
                    case "tag":
                        tag_content = get_tag_content(self.lexer_iter)
                        self.current_node.tag_content = tag_content
                        self._node_level_step_down()
        pass

    ####################################
    # main method for parser
    ####################################
    def parse(self, token_input: Generator[Token, None, None]) -> None:
        self.lexer_iter = token_input
        for token in token_input:
            token_category = token.type.split(".")[0]
            self.location = self.current_node.node_name.split(".")[-1]
            match token_category:
                case "keyword":
                    self._keyword_process_method(token)
                case "id":
                    self._id_process_method(token)
                case "space":
                    self._space_process_method(token)
                case "bracket":
                    self._bracket_process_method(token)
            pass

            logging.debug(f"NODE_NAME:{self.current_node.node_name}")
            if token.content == '\n':
                logging.debug("TOKEN:'newline'")
            else:
                logging.debug(f"TOKEN:'{token.content}'")
        pass

    def dump_ast(self) -> dict:
        return self.ast.dump()
    pass


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

    output = open("./test_ast.json", "w")
    print(dump_ast_json_form, file=output)
    output.close()
