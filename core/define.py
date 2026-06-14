class Token:

    def __init__(self, content="", type="") -> None:
        self.content: str = content
        self.type: str = type

    def set_content(self, content: str) -> None:
        self.content = content

    def set_type(self, token_type: str) -> None:
        self.type = token_type

    def __str__(self) -> str:
        return self.content


from dataclasses import dataclass
import tomllib
import os
from pathlib import Path
from typing import List


@dataclass
class FileManager:
    _base_dir: str = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    rules_file: str = "pyv_compiler/grammar/rules.toml"
    rules_dir: str = "pyv_compiler/grammar/rules"
    token_define_file: str = "pyv_compiler/grammar/token.toml"
    lookup_file: str = "pyv_compiler/grammar/production_lookup.toml"
    symbol_level_file: str = "pyv_compiler/grammar/symbol_level.toml"
    cg_rules_dir: str = "pyv_compiler/grammar/cg_rules"
    debug_log_file: str | None = "pyv_compiler/parser_debug.log"
    # debug_log_file: str | None = None

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


from .err import BracketMismatchError


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
            if rule_name == "file_rules":
                continue
            rule = GrammarRule(rule_name, **rule_dict)  # 解包字典
            self.rules[rule_name] = rule
        return self.rules


class Node:
    def __init__(self, node_name: str, **kwargs) -> None:
        self.node_name = node_name
        for key, value in kwargs.items():
            setattr(self, key, value)

    @staticmethod
    def _dump_item(item):
        # 递归处理 Node、dict、list，过滤 None 和空列表
        if isinstance(item, Node):
            return item.dump()
        if isinstance(item, dict):
            # 过滤掉值为 None 或空列表的键值对
            filtered = {}
            for k, v in item.items():
                if v is None:
                    continue
                if isinstance(v, list) and len(v) == 0:
                    continue
                dumped_v = Node._dump_item(v)
                if dumped_v is not None:
                    filtered[k] = dumped_v
            return filtered if filtered else None
        if isinstance(item, list):
            # 过滤掉列表中的 None 和空列表项
            filtered = [Node._dump_item(x) for x in item if x is not None]
            filtered = [
                x for x in filtered if x is not None
            ]  # 二次过滤（以防 _dump_item 返回 None）
            return filtered if filtered else None
        # 基本类型直接返回
        return item

    def dump(self):
        result = {}
        for attr, value in self.__dict__.items():
            # 跳过 node_name 字段（类型已由外层键隐含）
            if attr == "node_name":
                continue
            # 跳过值为 None 或空列表的属性
            if value is None:
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            # 递归处理值
            dumped = self._dump_item(value)
            if dumped is not None:
                result[attr] = dumped
        # 外层键仍使用 node_name 提供类型信息
        return {self.node_name: result}

    def add_sub_node(self, sub: "Node") -> None:
        if not hasattr(self, "sub_node"):
            self.sub_node = []
        self.sub_node.append(sub)

    def iter_children(self):
        seen = set()
        if hasattr(self, "sub_node"):
            seen.update(id(c) for c in self.sub_node)
            yield from self.sub_node
        for attr_name in vars(self):
            val = getattr(self, attr_name)
            if isinstance(val, Node):
                if id(val) not in seen:
                    seen.add(id(val))
                    yield val
                continue
            if not isinstance(val, list):
                continue
            for item in val:
                if isinstance(item, Node) and id(item) not in seen:
                    seen.add(id(item))
                    yield item

    def add_attr(self, attr_name: str, attr_value) -> None:
        setattr(self, attr_name, attr_value)

    def __str__(self) -> str:
        attrs = {k: v for k, v in self.__dict__.items()}
        return f'{self.node_name}({", ".join(f"{k}={v}" for k,v in attrs.items())})'

    def __repr__(self) -> str:
        return f'"{self.node_name}"'
