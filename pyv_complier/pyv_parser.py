from typing import Generator
import logging
import copy

from pyv_lexer import Token, Lexer, _read_token_define, _lex_input
from pyv_ast_node import Node, RootNode, ClassDefNode, PortListNode, TagNode, \
    InterfaceNode


logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s')


def get_types() -> list[str]:
    from os import walk
    _, types, _ = next(walk("./grammar/type"))
    return types


class Parser:
    def __init__(self, token_define: dict) -> None:
        self.token_define = token_define
        self.types = get_types()
        self.ast: RootNode = RootNode()

        # node level
        self.node_level: list[Node] = [self.ast]
        self.current_node = self.node_level[-1]
        self.location = "root"

        # temp port
        self.current_port: dict = {
            "port_name": "",
            "port_type": "",
            "port_width": 1,
            "port_param": [],
            "port_param_dict": {},
            "port_default_value": ""
        }

        # flag
        ...
        pass

    def _keyword_process_method(
        self,
        current_token: Token
    ) -> None:
        key_word_type = current_token.type.split(".")[2]
        match key_word_type:
            case "class":
                class_def_node: ClassDefNode = ClassDefNode()
                self.current_node.add_node(class_def_node)
                self.node_level.append(class_def_node)
                self.current_node = class_def_node
                self.current_node.update_class_name = True
                pass
            case "input" | "output" | "inout":
                port_list_node: PortListNode = PortListNode(key_word_type)
                self.current_node.add_node(port_list_node)
                self.node_level.append(port_list_node)
                self.current_node = port_list_node
                self.current_node.update_port_name = True
                pass
            case "tag":
                tag_node: TagNode = TagNode()
                self.current_node.add_node(tag_node)
                self.node_level.append(tag_node)
                self.current_node = tag_node
                pass

            case "interface":
                interface_node: InterfaceNode = InterfaceNode()
                self.current_node.add_node(interface_node)
                self.node_level.append(interface_node)
                self.current_node = interface_node
                self.current_node.update_if_name = True

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
                    self.current_node.bases_list.\
                        append(current_token.content)
                elif self.current_node.update_body is True:
                    pass
                pass

            case "port_list_input" | "port_list_output" | "port_list_inout":
                # decide id is name or type
                if current_token.content not in self.types \
                        and self.current_node.update_port_name is True:
                    self.current_node.update_port_name = False
                    self.current_node.update_port_type = True
                    self.current_port["port_name"] = current_token.content

                elif current_token.content in self.types \
                        and self.current_node.update_port_type is True:
                    self.current_node.update_port_type = False
                    self.current_port["port_type"] = current_token.content

                elif self.current_node.update_port_param is True\
                        and self.current_node.is_dict_param is False:
                    self.current_port["port_param"].append(
                        current_token.content)
                    pass

                elif self.current_node.update_port_param is True\
                        and self.current_node.is_dict_param is True:
                    pass
                    self.current_node.dict_param_name = current_token.content
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

    def _bracket_process_method(
        self,
        current_token: Token
    ) -> None:
        match self.location:
            case "class_define":
                if self.current_node.update_class_name is True\
                    and current_token.content == \
                        self.token_define["bracket"]["l_parentheses"]:
                    self.current_node.update_class_name = False
                    self.current_node.update_bases = True
                elif self.current_node.update_bases is True \
                        and current_token.content == \
                        self.token_define["bracket"]["r_parentheses"]:
                    self.current_node.update_bases = False
                pass
            case "port_list_input" | "port_list_output" | "port_list_inout":
                if current_token.content == \
                        self.token_define["bracket"]["l_parentheses"]:
                    self.current_node.update_port_param = True
                elif current_token.content == \
                        self.token_define["bracket"]["r_parentheses"]:
                    self.current_node.update_port_param = False

            case "tag":
                if current_token.content == \
                        self.token_define["bracket"]["l_parentheses"]:
                    self.current_node.update_tag_content = True
                elif current_token.content == \
                        self.token_define["bracket"]["r_parentheses"]:
                    self.current_node.update_tag_content = False
                    self.node_level.pop()
                    self.current_node = self.node_level[-1]
    pass

    def _op_process_method(
        self,
        current_token: Token
    ) -> None:
        match self.location:
            case "class_define":
                if current_token.content == \
                        self.token_define["op"]["base"]["colon"]:
                    self.current_node.update_body = True
                pass

            case "port_list_input" | "port_list_output" | "port_list_inout":
                if current_token.content == \
                        self.token_define["op"]["base"]["equal"]:
                    if self.current_node.update_port_param is True:
                        self.current_node.is_dict_param = True
                    else:
                        self.current_node.update_port_init_value = True
        pass

    def _literal_process_method(
        self,
        current_token: Token
    ) -> None:
        match self.location:
            case "port_list_input" | "port_list_output" | "port_list_inout":
                if self.current_node.update_port_param is True\
                        and self.current_node.is_dict_param is False:
                    self.current_port["port_param"].append(
                        current_token.content)
                    pass

                elif self.current_node.update_port_param is True\
                        and self.current_node.is_dict_param is True:
                    if "port_param" in self.current_port:
                        self.current_port["port_param_dict"][
                            self.current_port["port_param"][-1]] = \
                            current_token.content
                        del self.current_port["port_param"]
                    else:
                        self.current_port["port_param_dict"][
                            self.current_node.dict_param_name] = \
                            current_token.content
                        self.current_node.dict_param_name = ""
                    pass

                elif self.current_node.update_port_init_value is True:
                    self.current_port["port_default_value"] = \
                        current_token.content
                    self.current_node.update_port_init_value = False
                pass

            case "tag":
                if current_token.type == "literal.string":
                    self.current_node.add_tag_content(
                        current_token.content)
                pass
        pass

    def _space_process_method(
        self,
        current_token: Token
    ) -> None:
        space_type: str = current_token.type.split(".")[-1]
        match space_type:
            case "dedent":
                self.node_level.pop()
                self.current_node = self.node_level[-1]
                self.location = \
                    self.current_node.node_name.split(".")[-1]
                pass
        pass

    def _newline_process_method(self) -> None:
        match self.location:
            case "port_list_input" | "port_list_output" | "port_list_inout":

                if self.current_port["port_name"] != "":
                    port_copy = copy.deepcopy(self.current_port)
                    if "input" in self.location:
                        del port_copy["port_default_value"]
                    if self.current_node.is_dict_param is False:
                        del port_copy["port_param_dict"]
                    self.current_node.add_port(port_copy)
                    self.current_port = {
                        "port_name": "",
                        "port_type": "",
                        "port_width": 1,
                        "port_param": [],
                        "port_param_dict": {},
                        "port_default_value": ""
                    }
                    self.current_node.update_port_name = True
        pass

    def parse(self, token_input: Generator[Token, None, None]) -> None:
        for token in token_input:
            token_category = token.type.split(".")[0]
            self.location = self.current_node.node_name.split(".")[-1]
            match token_category:
                case "id":
                    token_verbose_category: str = token.type.split(".")[1]
                    if token_verbose_category == "keyword":
                        self._keyword_process_method(token)
                    else:
                        self._id_process_method(token)
                    ...
                case "op":
                    self._op_process_method(token)
                    ...
                case "bracket":
                    self._bracket_process_method(token)
                    ...
                case "literal":
                    self._literal_process_method(token)
                    ...
                case "space":
                    self._space_process_method(token)
                case "newline":
                    self._newline_process_method()
                case _:
                    ...

            # refresh node level
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
        pyv_lexer, input_string=parse_input_raw)

    pyv_parser.parse(parse_input)

    import json
    dump_ast_json_form = json.dumps(pyv_parser.ast.dump(), indent=4)

    output = open("./test_ast.json", "w")
    print(dump_ast_json_form, file=output)
    output.close()
    ...
