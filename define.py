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
import tomllib
import os
from pathlib import Path
from typing import List


@dataclass
class FileManager:
    _base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_file: str = "pyv_compiler/grammar/rules.toml"
    rules_dir: str = "pyv_compiler/grammar/rules"
    token_define_file: str = "pyv_compiler/grammar/token.toml"
    lookup_file: str = "pyv_compiler/grammar/production_lookup.toml"
    symbol_level_file: str = "pyv_compiler/grammar/symbol_level.toml"
    cg_rules_dir: str = "pyv_compiler/grammar/cg_rules"
    debug_log_file: str = "pyv_compiler/parser_debug.log"

    @classmethod
    def get_full_path(cls, relative_path: str) -> str:
        """Get absolute path from relative path"""
        return str(Path(cls._base_dir) / relative_path.lstrip("/"))

    @classmethod
    def read_file(cls, relative_path: str) -> str:
        """Read file content from relative path"""
        with open(cls.get_full_path(relative_path), "r", encoding="utf-8") as f:
            return f.read()

    @classmethod
    def write_file(cls, relative_path: str, content: str) -> None:
        """Write content to file at relative path"""
        with open(cls.get_full_path(relative_path), "w", encoding="utf-8") as f:
            f.write(content)

    @classmethod
    def exists(cls, relative_path: str) -> bool:
        """Check if file exists"""
        return os.path.exists(cls.get_full_path(relative_path))

    @classmethod
    def load_rules(cls, rules_file: str = "") -> dict:
        """Load grammar rules from a single TOML file (legacy)"""
        if rules_file == "":
            rules_file = cls.rules_file
        rules_content = cls.read_file(rules_file)
        return tomllib.loads(rules_content)

    @classmethod
    def load_all_toml(cls, dir_relative_path: str) -> dict:
        """
        加载指定目录下所有 .toml 文件并合并为一个 dict。
        文件按名称排序加载，同名 key 后者覆盖前者。
        file_rules 列表特殊处理：所有文件中的 file_rules 会合并为一个列表。
        以下划线 _ 开头的文件被跳过（可用于禁用或注释）。
        如果目录不存在或为空，返回空 dict。
        """
        dir_path = cls.get_full_path(dir_relative_path)
        merged: dict = {}
        all_file_rules: list = []
        if not os.path.isdir(dir_path):
            return merged
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".toml") or fname.startswith("_"):
                continue
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = tomllib.loads(f.read())
            # file_rules 特殊处理：跨文件合并
            fr = data.pop("file_rules", None)
            if fr:
                all_file_rules.extend(fr)
            merged.update(data)
        if all_file_rules:
            merged["file_rules"] = all_file_rules
        return merged


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
    def __init__(self, name: str, **kwargs):
        self.name = name
        # 必填字段，如果缺失则设为空列表/空字典
        self.production = kwargs.pop("production", [])
        self.node = kwargs.pop("node", {})
        # 可选字段，提供默认值
        self.end_case = kwargs.pop("end_case", [])
        self.inline = kwargs.pop("inline", False)
        self.pratt = kwargs.pop("pratt", False)
        # 剩余的所有未知属性也保存下来
        for key, value in kwargs.items():
            setattr(self, key, value)

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

    def __init__(self) -> None:
        self.rules: dict[str, GrammarRule] = {}

    def rules_registration(self, rules_dir: str = "") -> dict[str, GrammarRule]:
        """
        加载语法规则：优先从目录加载所有 .toml 文件，
        目录不存在或为空时回退到单文件 rules.toml。
        :param rules_dir: 规则目录的相对路径
        """
        if rules_dir == "":
            rules_dir = FileManager.rules_dir
        rules_dict = FileManager.load_all_toml(rules_dir)
        if not rules_dict:
            # 回退：单文件加载
            rules_dict = FileManager.load_rules()
        for rule_name, rule_dict in rules_dict.items():
            rule = GrammarRule(rule_name, **rule_dict)  # 解包字典
            self.rules[rule_name] = rule
        return self.rules


class Node:
    def __init__(self, name: str, **kwargs) -> None:
        self.name = name
        for key, value in kwargs.items():
            setattr(self, key, value)

    @staticmethod
    def _dump_item(item):
        if isinstance(item, Node):
            return item.dump()
        if isinstance(item, dict):
            return {k: Node._dump_item(v) for k, v in item.items()}
        if isinstance(item, list):
            return [Node._dump_item(x) for x in item]
        return item

    def dump(self):
        # 收集除 name 和 child 外的所有属性
        attrs = {k: v for k, v in self.__dict__.items() if k not in ("name", "child")}
        has_children = hasattr(self, "child") and getattr(self, "child") is not None

        # 如果没有任何属性且没有子节点，直接返回节点名称
        if not attrs and not has_children:
            return self.name

        # 否则构建字典
        result = {}
        for attr, value in self.__dict__.items():
            if attr == "name":
                continue
            if isinstance(value, list):
                result[attr] = [self._dump_item(item) for item in value]
            elif isinstance(value, dict):
                result[attr] = {k: self._dump_item(v) for k, v in value.items()}
            else:
                result[attr] = value.dump() if isinstance(value, Node) else value
        return {self.name: result}

    def inherit(self, node: "Node") -> None:
        for attr, value in node.__dict__.items():
            if attr == "name":
                continue
            if isinstance(value, list):
                if not hasattr(self, attr):
                    setattr(self, attr, [])
                getattr(self, attr).extend(value)
            else:
                setattr(self, attr, value)

    def add_child(self, child: "Node") -> None:
        if not hasattr(self, "child"):
            setattr(self, "child", [])
        getattr(self, "child").append(child)

    def add_attr(self, attr_name: str, attr_value) -> None:
        if attr_name == "name" and self.name != "root":
            # 避免覆盖节点类型名，改用 identifier
            attr_name = "identifier"
        setattr(self, attr_name, attr_value)

    def __str__(self) -> str:
        attrs = {k: v for k, v in self.__dict__.items() if k != "name"}
        return f'{self.name}({", ".join(f"{k}={v}" for k,v in attrs.items())})'

    def __repr__(self) -> str:
        return f'"{self.name}"'
