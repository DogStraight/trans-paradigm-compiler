from abc import ABC


class Node(ABC):
    pass


class RootNode(Node):
    body: list

    def __init__(self):
        self.body = []
    pass
