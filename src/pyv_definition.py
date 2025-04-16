class Token:
    class Position:
        def __init__(self):
            self.line = 0
            self.column = 0

    def __init__(self) -> None:
        self.content: str = ""
        self.type: str = ""
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
    def __init__(self, name: str) -> None:
        self.name = name
        pass

    def dump(self) -> dict:
        dump_dict = {}
        for attr, value in self.__dict__.items():
            if isinstance(value, list):
                dump_dict[attr] = [
                    item.dump() if isinstance(item, Node) else item for item in value
                ]
            else:
                dump_dict[attr] = value.dump() if isinstance(value, Node) else value
        return {self.name: dump_dict}


class GrammarRule:
    def __init__(
        self,
        name: str,
        keywords: list[str],
        production: list[str],
        node_info: dict,
    ) -> None:
        self.name = name
        self.keywords = keywords
        self.production:list[str] = production
        self.node_info = node_info
        pass

    def dump(self) -> dict:
        return {
            self.name: {
                "keywords": self.keywords,
                "production": self.production,
                "node_info": self.node_info,
            }
        }
