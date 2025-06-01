class Token:
    class Position:
        def __init__(self):
            self.line = 0
            self.column = 0

    def __init__(self, content="", type="") -> None:
        self.content: str = content
        self.type: str = type
        self.start: Token.Position = Token.Position()
        self.end: Token.Position = Token.Position()

    def set_content(self, content: str) -> None:
        self.content = content

    def set_location(
        self, start_line: int, start_column: int, end_line: int, end_column: int
    ) -> None:
        self.start.line = start_line
        self.start.column = start_column
        self.end.line = end_line
        self.end.column = end_column

    def set_type(self, token_type: str) -> None:
        self.type = token_type


class Node:
    def __init__(self, name: str, **kwargs) -> None:
        self.name = name
        for key, value in kwargs.items():
            setattr(self, key, value)

    def dump(self) -> dict:
        dump_dict = {}
        for attr, value in self.__dict__.items():
            if attr == 'name':
                continue
            if isinstance(value, list):
                dump_dict[attr] = [
                    item.dump() if isinstance(item, Node) else item for item in value
                ]
            else:
                dump_dict[attr] = value.dump() if isinstance(value, Node) else value
        return {self.name: dump_dict}

    def __str__(self) -> str:
        attrs = {k:v for k,v in self.__dict__.items() if k != 'name'}
        return f"{self.name}({', '.join(f'{k}={v}' for k,v in attrs.items())})"

    def __repr__(self) -> str:
        attrs = {k:v for k,v in self.__dict__.items() if k != 'name'}
        return f"<Node {self.name} {attrs}>"


class GrammarRule:
    def __init__(
        self,
        name: str,
        production: list[str],
        node: dict,
    ) -> None:
        self.name = name
        self.production: list[str] = production
        self.node = node
        pass

    def dump(self) -> dict:
        return {
            self.name: {
                "production": self.production,
                "node": self.node,
            }
        }
