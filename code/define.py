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


from dataclasses import dataclass
import toml
import os
from pathlib import Path
from typing import Union


@dataclass
class FileManager:
    _base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_file: str = "/grammar/rules.toml"
    token_define_file: str = "/grammar/token.toml"
    lookup_file: str = "/grammar/production_lookup.toml"
    test_lookup_file: str = "/grammar/test_production_lookup.toml"

    @classmethod
    def get_full_path(cls, relative_path: str) -> str:
        """Get absolute path from relative path"""
        return str(Path(cls._base_dir) / relative_path.lstrip("/"))

    @classmethod
    def read_file(cls, relative_path: str) -> str:
        """Read file content from relative path"""
        with open(cls.get_full_path(relative_path), "r") as f:
            return f.read()

    @classmethod
    def write_file(cls, relative_path: str, content: Union[str, dict]) -> None:
        """Write content to file at relative path"""
        with open(cls.get_full_path(relative_path), "w") as f:
            if isinstance(content, dict):
                import toml

                toml.dump(content, f)
            else:
                f.write(content)

    @classmethod
    def exists(cls, relative_path: str) -> bool:
        """Check if file exists"""
        return os.path.exists(cls.get_full_path(relative_path))

    @classmethod
    def load_rules(cls, rules_file: str = "") -> dict:
        """Load grammar rules from TOML file"""
        if rules_file == "":
            rules_file = cls.rules_file
        rules_content = cls.read_file(rules_file)
        return toml.loads(rules_content)


def load_rule(name, rule_content) -> GrammarRule:
    return GrammarRule(
        name=name,
        production=rule_content["production"],
        end_case=rule_content["end_case"],
        node=rule_content["node"],
    )


from err import BracketMismatchError


def get_close_bracket_string(start_bracket: str, target_string: str) -> str:
    close_bracket = ""
    close_bracket_dict = {"(": ")", "[": "]", "{": "}", "<": ">"}
    # check if start_bracket is valid
    if start_bracket not in close_bracket_dict:
        raise BracketMismatchError(f"Invalid start bracket: {start_bracket}")

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
        raise BracketMismatchError(f"Invalid bracket pair in {target_string}")
    return extract_string[1:-1]


class GrammarRule:
    def __init__(
        self,
        name: str,
        production: list[str],
        end_case: list[str],
        node: dict,
    ) -> None:
        self.name = name
        self.production: list[str] = production
        self.end_case: list[str] = end_case
        self.node = node
        pass

    def dump(self) -> dict:
        return {
            self.name: {
                "production": self.production,
                "node": self.node,
            }
        }

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return f"<GrammarRule {self.name}>"


class GrammarRulesRegister:
    def __init__(self):
        self.rules = {}

    def rules_registration(self) -> dict[str, GrammarRule]:
        rules_dict = FileManager.load_rules()
        for rule_name, rule_dict in rules_dict.items():
            rule: GrammarRule = GrammarRule(
                rule_name,
                rule_dict["production"],
                rule_dict["end_case"],
                rule_dict["node"],
            )
            self.rules[rule_name] = rule
        return self.rules


class Node:
    def __init__(self, name: str, **kwargs) -> None:
        self.name = name
        for key, value in kwargs.items():
            setattr(self, key, value)

    def dump(self) -> dict:
        dump_dict = {}
        for attr, value in self.__dict__.items():
            if attr == "name":
                continue
            if isinstance(value, list):
                dump_dict[attr] = [
                    item.dump() if isinstance(item, Node) else item for item in value
                ]
            else:
                dump_dict[attr] = value.dump() if isinstance(value, Node) else value
        return {self.name: dump_dict}

    def __str__(self) -> str:
        attrs = {k: v for k, v in self.__dict__.items() if k != "name"}
        return f"{self.name}({', '.join(f'{k}={v}' for k,v in attrs.items())})"

    def __repr__(self) -> str:
        attrs = {k: v for k, v in self.__dict__.items() if k != "name"}
        return f"<Node {self.name} {attrs}>"
