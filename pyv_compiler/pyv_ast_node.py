from abc import ABCMeta, abstractmethod
import hashlib

from .pyv_lexer import Token


class Node(metaclass=ABCMeta):
    @abstractmethod
    def dump(self) -> dict:
        ...


class AttributeNode(Node):
    def __init__(self):
        self.node_name = "attribute"
        self.name: str = ""

    def dump(self) -> dict:
        dump_dict: dict = {}
        if isinstance(self.name, str):
            dump_dict["name"] = self.name
        else:
            dump_dict["name"] = self.name.dump()

        if hasattr(self, "attr"):
            dump_dict["attr"] = self.attr

        return {self.node_name: dump_dict}

    def add_name(self, name: str) -> None:
        self.name = name

    def add_attr(self, attr: str) -> None:
        self.attr = attr


class CallableNode(Node):
    def __init__(self):
        self.node_name = "callable"
        self.name: str = ""
        self.args: list = []
        self.kwargs: dict = {}
        self.return_type: str = ""
        # flag
        self.is_kwargs = False

    def dump(self) -> dict:
        dump_dict: dict = {}
        dump_dict["name"] = self.name
        if self.is_kwargs:
            dump_dict["kwargs"] = self.kwargs
        else:
            dump_dict["args"] = self.args
        return {self.node_name: dump_dict}

    def add_name(self, name: str) -> None:
        self.name = name

    def add_arg(self, arg: str) -> None:
        self.args.append(arg)

    def add_kwarg(self, key: str, value: str) -> None:
        self.kwargs[key] = value


class ExpressionNode(Node):
    def __init__(self):
        self.node_name = "expression"

    def dump(self):
        dump_dict: dict = {}

        # dump left operand
        if hasattr(self, "left_operand"):
            if isinstance(self.left_operand, Token):
                dump_dict["left_operand"] = {
                    "type": self.left_operand.type,
                    "content": self.left_operand.content}
            elif self.left_operand is not None:
                dump_dict["left_operand"] = self.left_operand.dump()

        # dump operator
        if hasattr(self, "operator"):
            dump_dict["operator"] = self.operator.type

        # dump right operand
        if hasattr(self, "right_operand"):
            if isinstance(self.right_operand, Token):
                dump_dict["right_operand"] = {
                    "type": self.right_operand.type,
                    "content": self.right_operand.content}
            elif self.right_operand is not None:
                dump_dict["right_operand"] = self.right_operand.dump()

        return {self.node_name: dump_dict}

    def add_operator(self, operator: Token):
        self.operator = operator

    def add_left_operand(self, operand: Node | Token):
        self.left_operand = operand

    def add_right_operand(self, operand: Node | Token):
        self.right_operand = operand

    def set_type(self, type: str):
        self.type = type


class StatementNode(Node):
    def __init__(self):
        self.node_name = "statement"
        self.body = []

    @abstractmethod
    def dump(self):
        ...


class RootNode(Node):
    def __init__(self):
        self.node_name = "root"
        self.file_name = ""
        self.time_scale_unit = "1ns"
        self.time_scale_accuracy = "1ps"
        self.body = []

    def dump(self) -> dict:
        dump_dict: dict = {}
        dump_dict["file_name"] = self.file_name
        dump_dict["time_scale_unit"] = self.time_scale_unit
        dump_dict["time_scale_accuracy"] = self.time_scale_accuracy
        dump_dict["body"] = {}
        for node in self.body:
            dump_dict["body"].update(node.dump())
        return {self.node_name: dump_dict}

    def add_node(self, node) -> None:
        self.body.append(node)


class ClassDefNode(StatementNode):
    def __init__(self):
        super().__init__()
        self.node_name += ".class_define"
        self.class_name: str = ""
        self.bases_list: list[str] = []

    def dump(self) -> dict:
        dump_dict: dict = {}
        dump_dict["class_name"] = self.class_name
        dump_dict["bases_list"] = self.bases_list
        dump_dict["body"] = {}
        for node in self.body:
            dump_dict["body"].update(node.dump())
        return {self.node_name: dump_dict}

    def add_bases(self, bases: str):
        self.bases.append(bases)
        pass

    def add_node(self, node) -> None:
        self.body.append(node)


class PortListNode(Node):
    def __init__(self, list_type: str):
        self.node_name = "port_list" + f"_{list_type}"
        self.port: list = []

        # flag for update
        self.update_port_name: bool = True
        self.update_port_type: bool = False

        # temp store for port init value
        self.port_init_var: int = 0

        # for param type
        self.is_dict_param: bool = False
        self.dict_param_name: str = ""

    def dump(self) -> dict:
        dump_dict: dict = {}
        dump_dict["node_name"] = self.node_name
        dump_dict["port"] = []
        for port in self.port:
            dump_dict["port"].append(port)
        return {self.node_name: dump_dict}

    def add_port(self, port: tuple):
        self.port.append(port)
        pass


class InterfaceNode(Node):
    def __init__(self):
        self.node_name = "interface"
        self.interface = []

        # flag for update
        self.update_if_name: bool = False
        self.update_if_type: bool = False
        self.update_if_param: bool = False

    def dump(self) -> dict:
        dump_dict: dict = {}
        dump_dict["node_name"] = self.node_name
        dump_dict["port"] = []
        for port in self.port:
            dump_dict["port"].append(port)
        return dump_dict

    def add_interface(self, interface) -> None:
        self.interface.append(interface)


class TagNode(StatementNode):
    def __init__(self):
        super().__init__()
        self.node_name += ".tag"
        self.tag_content: str = ""
        self.tag_hash: str = ""

        # update flags
        self.update_tag_content: bool = False

    def add_tag_content(self, content: str):
        self.tag_content = content
        hash_object = hashlib.sha256(content.encode())
        self.tag_hash = hash_object.hexdigest()

    def dump(self) -> dict:
        dump_dict = {}
        dump_dict["tag_content"] = self.tag_content
        dump_dict["tag_hash"] = self.tag_hash
        return {self.node_name: dump_dict}


class AlffNode(StatementNode):

    def __init__(self):
        super().__init__()
        self.node_name += ".alff"
        self.clk_name: str = ""
        self.rst_name: str = ""
        self.clk_edge: str = ""
        self.rst_active: str = ""

    def add_clk_name(self, clk_name: str):
        self.clk_name = clk_name

    def add_rst_name(self, rst_name: str):
        self.rst_name = rst_name

    def add_clk_edge(self, clk_edge: str):
        self.clk_edge = clk_edge

    def dump(self) -> dict:
        dump_dict = {}
        dump_dict["clk_name"] = self.clk_name
        dump_dict["rst_name"] = self.rst_name
        dump_dict["clk_edge"] = self.clk_edge
        return {self.node_name: dump_dict}

    def add_node(self, node) -> None:
        self.body.append(node)


class AlcombNode(StatementNode):
    def __init__(self):
        super().__init__()
        self.node_name += ".alcomb"


class IfNode(StatementNode):
    def __init__(self):
        super().__init__()
        self.update_if_condition = True

        # condition
        self.if_condition: ExpressionNode = None
        self.else_if_condition: list = []

        # stmt
        self.if_stmt: list = []
        self.else_if_stmt: dict[StatementNode, list] = {}
        self.else_stmt: list = []

    def add_if_condition(self, condition: ExpressionNode):
        self.if_condition = condition

    def add_if_stmt(self, if_stmt: StatementNode):
        self.if_stmt.append(if_stmt)

    def add_else_if_condition(self, condition: ExpressionNode):
        self.else_if_condition.append(condition)

    def add_else_if_stmt(self, else_if_stmt: StatementNode):
        if self.else_if_condition is not None:
            self.else_if_stmt[self.else_if_condition[-1]].append(else_if_stmt)

    def add_else_stmt(self, else_stmt: StatementNode):
        self.else_stmt = else_stmt

    def dump(self) -> dict:
        dump_dict = {}
        dump_dict["if_condition"] = self.if_condition.dump()
        dump_dict["if_stmt"] = []
        for s in self.if_stmt:
            dump_dict["if_stmt"].append(s.dump())
        if self.else_if_condition is not None:
            dump_dict["else_if_condition"] = []
            for condition in self.else_if_condition:
                dump_dict["else_if_condition"].append(condition.dump())
            dump_dict["else_if_stmt"] = {}
            for condition, stmt in self.else_if_stmt.items():
                dump_dict["else_if_stmt"][condition.dump()] = []
                for s in stmt:
                    dump_dict["else_if_stmt"][
                        condition.dump()].append(s.dump())
        if self.else_stmt is not None:
            dump_dict["else_stmt"] = self.else_stmt.dump()
        return {self.node_name: dump_dict}


# maybe need to add more keyword node
keyword_node_index = {
    "class": ClassDefNode,
    "input": [PortListNode, "input"],
    "output": [PortListNode, "output"],
    "inout": [PortListNode, "inout"],
    "interface": InterfaceNode,
    "tag": TagNode,
    "alff": AlffNode,
    "alcomb": AlcombNode,
    "if": IfNode,
}


class AssignmentNode(StatementNode):
    def __init__(self):
        super().__init__()
        self.node_name += ".assignment"
        self.left_hand_side = None
        self.right_hand_side: ExpressionNode = None

    def add_left_hand_side(self, left_hand_side):
        self.left_hand_side = left_hand_side

    def add_right_hand_side(self, right_hand_side: ExpressionNode):
        self.right_hand_side = right_hand_side

    def dump(self) -> dict:
        dump_dict = {}
        dump_dict["left_hand_side"] = self.left_hand_side.dump()
        dump_dict["right_hand_side"] = self.right_hand_side.dump()
        return {self.node_name: dump_dict}
