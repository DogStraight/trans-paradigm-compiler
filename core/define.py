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
                print(
                    f"⚠️ [加载] {fname} 覆盖了之前文件中的规则: "
                    f"{', '.join(sorted(overlaps))}",
                    file=__import__("sys").stderr,
                )
            merged.update(data)
        if all_file_rules:
            merged["file_rules"] = all_file_rules
        return merged


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

    # 从 parser/analyzer 阶段提取的字段名集合
    _KNOWN_FIELDS = {
        "production",
        "node",
        "end_case",
        "inline",
        "pratt",
        "atomic",
        "block_start",
        "block_end",
        "scope",
        "symbol",
        "identifier_ref",
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

    @staticmethod
    def _has_top_level_choice(prod: str) -> bool:
        """检测 production 字符串中是否有顶层的 |（不在括号/分组内）"""
        depth = 0
        for ch in prod:
            if ch == '(': depth += 1
            elif ch == ')': depth -= 1
            elif ch == '|' and depth == 0:
                return True
        return False

    def inject_productions(self, inject_config: dict[str, list[str]]) -> None:
        """
        将增强规则的 alternative 注入到语法规则的分支列表中。

        两层注入：
        1. 直接注入：将 alternative 追加到规则自身的 production 分支（原模式）
        2. 传播注入：找到所有引用了本规则的 production，把 @RuleName 替换为
           @TypedDecl|@AnsiPortDecl 形式，实现"先匹配增强语法，再降级原始语法"

        inject_config: { "RuleName": ["@ExtRule1", "@ExtRule2"] }
        """
        # ── 第一层：修改规则自身 production ──
        for rule_name, alternatives in inject_config.items():
            if rule_name not in self.rules:
                print(f"⚠️ [inject] 规则 {rule_name} 不存在，跳过注入")
                continue
            rule = self.rules[rule_name]
            prods = list(getattr(rule, "production", []))
            if not prods:
                continue
            # 将 alternative 作为分支追加到第一个 production 元素
            first_prod = prods[0]
            if isinstance(first_prod, str):
                for alt in alternatives:
                    if self._has_top_level_choice(first_prod):
                        first_prod = f"{alt}|{first_prod}"  # 前置（优先匹配）
                    else:
                        first_prod += f"|{alt}"
                prods[0] = first_prod
                object.__setattr__(rule, "production", tuple(prods))

        # ── 第二层：传播到引用该规则的所有 production ──
        for rule_name, alternatives in inject_config.items():
            target_ref = f"@{rule_name}"
            for other_name, other_rule in self.rules.items():
                if other_name in inject_config:
                    continue  # 自身已处理
                other_prods = list(getattr(other_rule, "production", []))
                changed = False
                for i, prod in enumerate(other_prods):
                    if not isinstance(prod, str):
                        continue
                    for alt in alternatives:
                        # 将 @RuleName 替换为 (@ExtRule|@RuleName)
                        # 括号保证 | 分支不会与相邻元素意外结合（如 (symbol.base.comma,...)* 中的逗号）
                        replacement = f"({alt}|{target_ref})"
                        if target_ref in prod:
                            prod = prod.replace(target_ref, replacement)
                            changed = True
                    other_prods[i] = prod
                if changed:
                    object.__setattr__(other_rule, "production", tuple(other_prods))
                    print(f"  ↳ [inject] 传播到 {other_name}: {other_prods}")

    def inject_productions_replace(
        self, replace_config: dict[str, dict[str, str]]
    ) -> None:
        """
        替换指定规则的 production 或 end_case 中匹配的字符串。
        replace_config: { "RuleName": { "old": "目标字符串", "new": "新字符串" } }
        若 old 以 "end_case = " 为前缀，则匹配并替换 end_case 属性，
        否则匹配并替换 production 元素。
        """
        for rule_name, spec in replace_config.items():
            if rule_name not in self.rules:
                print(f"⚠️ [inject/replace] 规则 {rule_name} 不存在，跳过")
                continue
            rule = self.rules[rule_name]
            old_str = spec.get("old", "")
            new_str = spec.get("new", "")
            if not old_str:
                continue

            # 判断替换目标：end_case 还是 production
            ec_prefix = 'end_case = '
            if old_str.startswith(ec_prefix):
                old_ec = old_str[len(ec_prefix):]
                new_ec = new_str[len(ec_prefix):]
                # end_case 是列表，序列化为字符串比较
                import json as _json
                current = list(getattr(rule, "end_case", []))
                old_list = _json.loads(old_ec)
                if current == old_list:
                    new_list = _json.loads(new_ec)
                    object.__setattr__(rule, "end_case", tuple(new_list))
                    print(f"  ↳ [inject/replace] {rule_name}.end_case: {new_list}")
                else:
                    print(f"  ⚠️ [inject/replace] {rule_name}.end_case 不匹配: 当前={current}, 期望={old_list}")
            else:
                prods = list(getattr(rule, "production", []))
                changed = False
                for i, prod in enumerate(prods):
                    if isinstance(prod, str) and old_str in prod:
                        prods[i] = prod.replace(old_str, new_str)
                        changed = True
                if changed:
                    object.__setattr__(rule, "production", tuple(prods))
                    print(f"  ↳ [inject/replace] {rule_name}: {prods}")


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
