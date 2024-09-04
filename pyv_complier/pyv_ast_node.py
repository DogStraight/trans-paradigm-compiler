from abc import ABCMeta, abstractmethod
import hashlib


class Node(metaclass=ABCMeta):
    @abstractmethod
    def dump(self) -> dict:
        ...


class ExpressionNode(Node):
    def __init__(self):
        self.node_name = "expression"
        self.value = ""
        self.body = []

    @abstractmethod
    def dump(self):
        ...

    @abstractmethod
    def add_node(self, node):
        ...


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


class VariableNode(ExpressionNode):
    def __init__(self, var_id):
        self.node_name = "variable"
        self.var_id = var_id
        self.var_scope = ""

        # for gc flag
        self.ctx_type = "store"
    pass

    def dump(self):
        dump_dict: dict = {}
        dump_dict["var_id"] = self.var_id
        dump_dict["var_scope"] = self.var_scope
        dump_dict["ctx_type"] = self.ctx_type
        return {self.node_name: dump_dict}
        ...

    def add_node(self):
        # do nothing it is the endmost node
        ...

    def set_var_scope(self, scope: str):
        self.scope = scope
        pass


class ClassDefNode(StatementNode):
    def __init__(self):
        super().__init__()
        self.node_name += ".class_define"
        self.class_name: str = ""
        self.bases_list: list[str] = []
        # update flags
        self.update_class_name: bool = False
        self.update_bases: bool = False
        self.update_body: bool = False

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
        self.port: list[tuple] = []

        # flag for update
        self.update_port_name: bool = False
        self.update_port_type: bool = False
        self.update_port_param: bool = False
        self.update_port_init_value: bool = False

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
        pass

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

    def add_node(self, node):
        pass

    def dump(self) -> dict:
        dump_dict = {}
        dump_dict["tag_content"] = self.tag_content
        dump_dict["tag_hash"] = self.tag_hash
        return {self.node_name: dump_dict}


if __name__ == "__main__":
    test_node = RootNode()
    print(test_node.dump())
