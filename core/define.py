"""Core type definitions: Token, GrammarRule, GrammarRulesRegister, Node.

These types are shared across all pipeline stages — Lexer produces Token,
Parser consumes Token and produces Node (AST), GrammarRule drives both
parsing and rendering.
"""

class Token:

    def __init__(self, content="", type="", line=0, column=0) -> None:
        self.content: str = content
        self.type: str = type
        self.line: int = line
        self.column: int = column

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
    rules_file: str = "pyv_compiler/grammar/rules_verilog/base/token.toml"
    rules_dir: str = "pyv_compiler/grammar/rules_verilog"
    token_define_file: str = "pyv_compiler/grammar/rules_verilog/base/token.toml"
    lookup_file: str = "pyv_compiler/grammar/rules_verilog/base/production_lookup.toml"

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
        支持递归子目录（子目录名不以下划线开头且不含 . 时递归）。
        文件按名称排序加载，同名 key 后者覆盖前者。
        file_rules 列表特殊处理：所有文件中的 file_rules 会合并为一个列表。
        以下划线 _ 开头的文件/目录被跳过。
        如果目录不存在或为空，返回空 dict。
        """
        dir_path = cls.get_full_path(dir_relative_path)
        merged: dict = {}
        all_file_rules: list = []
        if not os.path.isdir(dir_path):
            return merged
        for fname in sorted(os.listdir(dir_path)):
            if fname.startswith("_"):
                continue
            fpath = os.path.join(dir_path, fname)
            # 子目录递归
            if os.path.isdir(fpath) and "." not in fname:
                sub = cls.load_all_toml(
                    os.path.join(dir_relative_path, fname).replace("\\", "/")
                )
                for k, v in sub.items():
                    if k == "file_rules":
                        all_file_rules.extend(v)
                    else:
                        merged[k] = v
                continue
            if not fname.endswith(".toml"):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                data = tomllib.loads(f.read())
            # file_rules 特殊处理：跨文件合并
            fr = data.pop("file_rules", None)
            if fr:
                all_file_rules.extend(fr)
            # 检测跨文件重名覆盖
            overlaps = merged.keys() & data.keys()
            if overlaps:
                import sys as _sys
                print(
                    f"[loader] {fname} overwrites previous rules: "
                    f"{', '.join(sorted(overlaps))}",
                    file=_sys.stderr,
                )
            merged.update(data)
        if all_file_rules:
            merged["file_rules"] = all_file_rules
        return merged


class ParseError(Exception):
    """解析错误，携带失败上下文以便快速定位。

    Attributes:
        msg: 人类可读的错误描述
        token: 失败时的当前 Token（可为 None）
        rule: 正在尝试匹配的规则名（可为 None）
        path: 当前语义路径（可为 None）
        candidates: 候选规则列表（可为 None）
        context_info: 解析上下文摘要（token 指针等）
    """

    def __init__(
        self,
        msg: str = "",
        token=None,
        rule: str | None = None,
        path: str | None = None,
        candidates: list | None = None,
        context_info: str | None = None,
    ):
        self.token = token
        self.rule = rule
        self.path = path
        self.candidates = candidates
        self.context_info = context_info
        # 构建详细信息
        parts = [msg]
        if token:
            parts.append(f"  token: '{token.content}' (type={token.type}) Ln {token.line}")
        if rule:
            parts.append(f"  rule: {rule}")
        if path:
            parts.append(f"  path: {path}")
        if candidates is not None:
            parts.append(f"  candidates ({len(candidates)}): {[r.name if hasattr(r, 'name') else str(r) for r in candidates]}")
        if context_info:
            parts.append(f"  ctx: {context_info}")
        super().__init__("\n".join(parts))


class BracketMismatchError(Exception):
    pass


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
    """语法规则

    由 TOML 文件加载，除标准的 production/node/end_case 外，
    可通过自声明属性附加语义角色，供下游消费（不限于 SemanticAnalyzer）：

    ───────────────────────────────────────────────────────────────
    语义自声明属性 (semantic_analyzer.py 消费)
    ───────────────────────────────────────────────────────────────
    scope = { name_attr?, kind? }    本规则创建新作用域
        name_attr  从节点某属性提取作用域名称（缺省用规则名）
        kind       作用域种类（缺省 "block"）

    symbol = { kind, name_attr }     本规则在作用域中注册符号
        kind       符号种类（如 "wire" / "reg" / "port"）
        name_attr  从节点提取符号名的属性路径

    identifier_ref = true    本规则的产出节点是标识符引用（触发作用域链解析 + _symbol_ref 绑定）
    ───────────────────────────────────────────────────────────────

    其他属性由 Parser / Renderer / Normalizer 各自消费。
    """

    # 从 parser/analyzer 阶段提取到顶层的字段名集合
    # 只包含 Parser/Renderer 消费的字段，analyzer 专用字段留在 rule.analyzer 中
    _KNOWN_FIELDS = {
        "production",
        "node",
        "end_case",
        "inline",
        "pratt",
        "atomic",
        "is_block",
    }
    # 默认值为列表的字段
    _LIST_FIELDS = {"production", "node", "end_case"}

    def __init__(self, name: str, **kwargs):
        self.name = name

        # 设置默认值
        for fld in self._KNOWN_FIELDS:
            if fld in self._LIST_FIELDS:
                setattr(self, fld, [])
            else:
                setattr(self, fld, False)

        # 从嵌套的阶段结构中提取属性到顶层，同时保留原始嵌套
        for stage in ("parser", "analyzer", "renderer"):
            stage_data = kwargs.pop(stage, {})
            if stage_data:
                setattr(self, stage, stage_data)
                for k, v in stage_data.items():
                    if k in self._KNOWN_FIELDS:
                        # node 只接受 dict 类型
                        if k == "node" and not isinstance(v, dict):
                            continue
                        setattr(self, k, v)

        # 剩余未识别的属性
        for key, value in kwargs.items():
            setattr(self, key, value)

    def has_pass_end_case(self) -> bool:
        """检查是否有正匹配的 end_case 项（非 ! 前缀）。

        用于 statement_rule_names 过滤：仅含 ! 前缀的 end_case 不应视为语句级规则。
        """
        ec = getattr(self, "end_case", [])
        return any(isinstance(item, str) and not item.startswith("!") for item in ec)

    def dump(self) -> dict:
        return {
            self.name: {
                "production": getattr(self, "production", []),
                "node": getattr(self, "node", None),
            }
        }

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return f"<GrammarRule {self.name}>"


class GrammarRulesRegister:

    def __init__(self) -> None:
        self.rules: dict[str, GrammarRule] = {}

    @staticmethod
    def _resolve_peek(rules_dict: dict) -> dict:
        """解析跨阶段窥视引用（peek）。

        在 TOML 中使用：
            [RuleName.parser]
            peek = { scope = "analyzer", symbol = "analyzer" }

        加载期将 analyzer.scope 拷贝到 parser.scope，
        不增加运行期耦合。
        """
        import copy
        for rule_name, rule_dict in rules_dict.items():
            if rule_name == "file_rules":
                continue
            parser = rule_dict.get("parser")
            if not isinstance(parser, dict):
                continue
            peek = parser.pop("peek", None)
            if not isinstance(peek, dict):
                continue
            for target_field, source_stage_name in peek.items():
                source_stage = rule_dict.get(source_stage_name)
                if not isinstance(source_stage, dict):
                    raise ValueError(
                        f"peek: rule '{rule_name}' source stage "
                        f"'{source_stage_name}' not found or not a dict"
                    )
                value = source_stage.get(target_field)
                if value is None:
                    raise ValueError(
                        f"peek: rule '{rule_name}' field '{target_field}' "
                        f"not found in stage '{source_stage_name}'"
                    )
                parser[target_field] = copy.deepcopy(value)
        return rules_dict

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
        # 解析 peek 引用（加载期，不影响运行期隔离）
        rules_dict = self._resolve_peek(rules_dict)
        for rule_name, rule_dict in rules_dict.items():
            if rule_name == "file_rules":
                continue
            rule = GrammarRule(rule_name, **rule_dict)  # 解包字典
            self.rules[rule_name] = rule
        return self.rules


class Node:
    ERROR_NODE_NAME = "__error__"

    def __init__(self, node_name: str, **kwargs) -> None:
        self.node_name = node_name
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def is_error(self) -> bool:
        return self.node_name == self.ERROR_NODE_NAME

    @property
    def raw_text(self) -> str:
        if not self.is_error:
            return ""
        tokens = getattr(self, "raw_tokens", [])
        return " ".join(t.content for t in tokens)

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
            if attr == "node_name":
                continue
            if value is None:
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            if attr == "raw_tokens" and self.is_error:
                result["raw_text"] = self.raw_text
                continue
            dumped = self._dump_item(value)
            if dumped is not None:
                result[attr] = dumped
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
