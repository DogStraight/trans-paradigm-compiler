"""Core type definitions: Token, GrammarRule, GrammarRulesRegister, Node.

These types are shared across all pipeline stages — Lexer produces Token,
Parser consumes Token and produces Node (AST), GrammarRule drives both
parsing and rendering.
"""

import json
import tomllib
import os
from pathlib import Path

# ── 配置文件查找路径 ──
_CONFIG_CANDIDATES = ["config/pyv_config.json"]


def _find_user_config() -> str:
    """Find the project configuration file.

    Search order:
        1. $PYV_CONFIG env var (explicit override)
        2. From CWD upward: config/pyv_config.json
    """
    # 1. Env var override
    env_path = os.environ.get("PYV_CONFIG")
    if env_path:
        path = os.path.abspath(env_path)
        if os.path.isfile(path):
            return path

    # 2. Walk up from CWD
    cwd = os.path.abspath(os.getcwd())
    parent = cwd
    while True:
        for name in _CONFIG_CANDIDATES:
            path = os.path.join(parent, name)
            if os.path.isfile(path):
                return path
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent

    # 3. Global fallback
    return ""


def _load_pyv_meta() -> dict:
    """加载项目配置。

    架构：
        pyv_config.json（用户配置）→ 选择语法包
            └── grammar/<rules_dir>/pyv.toml（语法包自带引擎接口配置）
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Step 1: Load user config to find grammar package
    user_config = _find_user_config()
    if user_config:
        try:
            with open(user_config, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"[config] {user_config} parse failed: {e}")
    else:
        cfg = {}

    # Step 2: Resolve grammar package path
    # pyv_config.json 中 grammar 可以是字符串（路径）或旧格式对象
    grammar_val = cfg.get("grammar", "")
    if isinstance(grammar_val, str):
        grammar_dir = grammar_val
    elif isinstance(grammar_val, dict):
        grammar_dir = grammar_val.get("rules_dir", "")
    else:
        grammar_dir = ""

    # Step 3: Load grammar package pyv.toml for engine interface config
    meta_path = os.path.join(root, grammar_dir, "pyv.toml")
    meta: dict = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = tomllib.loads(f.read())
        except tomllib.TOMLDecodeError as e:
            raise RuntimeError(f"[config] {grammar_dir}/pyv.toml parse failed: {e}")

    # Step 4: 自动发现 ext 目录（<grammar_dir>/ext/pyv.toml）
    ext_dirs: list[str] = []
    ext_candidate = os.path.join(root, grammar_dir, "ext", "pyv.toml")
    if os.path.isfile(ext_candidate):
        ext_dirs.append(os.path.join(grammar_dir, "ext"))

    # Step 5: Normalize — grammar 统一为对象格式
    merged = dict(cfg)
    merged["grammar"] = {
        "rules_dir": grammar_dir,
        "ext_dirs": ext_dirs,
    }
    # pyv.toml 中其他 engine config 补入
    for k, v in meta.items():
        if k != "grammar":
            merged.setdefault(k, v)

    if "grammar" not in merged:
        raise RuntimeError(
            f"[config] No grammar package found.\n"
            f"  Create config/pyv_config.json or ensure {grammar_dir}/pyv.toml exists."
        )
    return merged


_pyv_meta = _load_pyv_meta()

# 增强语法层目录（来自 pyv.toml [grammar]）
DEFAULT_EXT_DIRS: list[str] = _pyv_meta["grammar"]["ext_dirs"]

# 核心语法规则目录（来自 pyv.toml [grammar]）
DEFAULT_RULES_DIR: str = _pyv_meta["grammar"]["rules_dir"]


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


class Node:

    def __init__(self, node_name: str, **kwargs) -> None:
        self.node_name = node_name
        for key, value in kwargs.items():
            setattr(self, key, value)

    @staticmethod
    def _dump_item(item):
        if isinstance(item, Node):
            return item.dump()
        if isinstance(item, dict):
            filtered = {
                k: Node._dump_item(v)
                for k, v in item.items()
                if v is not None and not (isinstance(v, list) and not v)
            }
            return filtered if filtered else None
        if isinstance(item, list):
            filtered = [Node._dump_item(x) for x in item if x is not None]
            filtered = [x for x in filtered if x is not None]
            return filtered if filtered else None
        return item

    def dump(self):
        result = {}
        for attr, value in self.__dict__.items():
            if attr == "node_name" or value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            dumped = Node._dump_item(value)
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


class FileManager:
    """纯静态工具类 — 文件路径管理与 TOML 加载。全局单例（无实例状态）。"""

    _base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_file: str = ""
    rules_dir: str = DEFAULT_RULES_DIR
    token_define_file: str = ""
    lookup_file: str = ""
    cg_rules_dir: str = ""
    debug_log_file: str | None = None

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
    def exists(cls, relative_path: str) -> bool:
        """Check if file exists"""
        return os.path.exists(cls.get_full_path(relative_path))

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
            if fname.startswith("_") or fname == "token.toml":
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
    """解析错误，携带失败上下文以便快速定位。"""

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
        parts = [msg]
        if token:
            parts.append(
                f"  token: '{token.content}' (type={token.type}) Ln {token.line}"
            )
        if rule:
            parts.append(f"  rule: {rule}")
        if path:
            parts.append(f"  path: {path}")
        if candidates is not None:
            names = [r.name if hasattr(r, "name") else str(r) for r in candidates]
            parts.append(f"  candidates ({len(candidates)}): {names}")
        if context_info:
            parts.append(f"  ctx: {context_info}")
        super().__init__("\n".join(parts))


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
        "production",  # 产生式列表，定义规则匹配什么
        "node",  # 属性映射，如何从匹配结果构建 AST 节点（$N 路径语法）
        "end_case",  # 终止符列表，匹配后检查的 token 边界
        "inline",  # 内联扁平化：只保留第一个子节点，消除包装节点
        "pratt",  # 使用 Pratt 解析器处理表达式（替换普通生产式匹配）
        "structure",  # 结构角色字典，展开为 is_block / is_statement / is_atom
    }
    # 默认值为列表的字段
    _LIST_FIELDS = {"production", "node", "end_case"}
    # 默认值为 None 的三态字段（未设置时由启发式或 False 兜底）
    _NONE_FIELDS = {"structure"}

    def __init__(self, name: str, **kwargs):
        self.name = name

        # 设置默认值
        for fld in self._KNOWN_FIELDS:
            if fld in self._LIST_FIELDS:
                setattr(self, fld, [])
            elif fld in self._NONE_FIELDS:
                setattr(self, fld, None)  # 三态：None=未设置
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

        # 从 structure 字典中计算 is_block / is_statement / is_atom
        #
        # TOML 写法:
        #   structure = { is_block = true }           — 块规则，走 parse_block
        #   structure = { is_statement = false }       — 非语句规则，排除出候选列表
        #   structure = { is_atom = true }             — 原子规则，不参与语句级匹配
        #
        # 真值表（唯一有效组合）:
        #   is_block  is_statement  is_atom   |  含义
        #   ──────────────────────────────────┼─────────────────
        #    false       None       false     |  普通规则（默认）
        #    false       None       true      |  原子规则（Number/Identifier）
        #    false       false      false     |  非语句规则（AnsiInputDecl）
        #    false       true       false     |  显式语句规则
        #    true        None       false     |  块规则（ModuleBlock）
        #    true        false      false     |  块但非语句（Root）
        #   ──────────────────────────────────┴─────────────────
        #   is_block + is_atom 同时为真不可能存在（互斥解析路径）
        struct = getattr(self, "structure", None) or {}
        self.is_block = struct.get("is_block", False)
        self.is_statement = struct.get("is_statement", None)
        self.is_atom = struct.get("is_atom", False)

    def has_pass_end_case(self) -> bool:
        """检查该规则是否为语句级规则。

        用于 statement_rule_names 过滤：
        - is_statement=True  → 明确标记为语句规则
        - is_statement=False → 明确排除
        - is_statement=None  → 未显式设置，回退到 end_case 启发式判断
        """
        stmt = getattr(self, "is_statement", None)
        if stmt is True:
            return True
        if stmt is False:
            return False
        # None：用 end_case 启发式
        ec = getattr(self, "end_case", [])
        return any(isinstance(item, str) and not item.startswith("!") for item in ec)

    def dump(self) -> dict:
        return {
            self.name: {
                "production": self.prods,
                "node": getattr(self, "node", None),
            }
        }

    def __str__(self) -> str:
        return f"{self.name}"

    def __repr__(self) -> str:
        return f"<GrammarRule {self.name}>"

    @property
    def prods(self) -> list:
        """生产式列表的快捷访问"""
        return getattr(self, "production", [])


class GrammarRulesRegister:
    """语法规则注册器 — 全局单例模式。

    主管线使用 GrammarRulesRegister.get_default() 获取共享实例，
    script/skill 等临时场景可创建独立实例 GrammarRulesRegister()。
    """

    _default_instance: "GrammarRulesRegister | None" = None

    @classmethod
    def get_default(cls) -> "GrammarRulesRegister":
        """获取全局默认单例实例。"""
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    def __init__(self) -> None:
        self.rules: dict[str, GrammarRule] = {}
        self._loaded_dirs: set[str] = set()

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

        支持缓存：已加载过的目录跳过磁盘 IO，直接使用 self.rules。
        :param rules_dir: 规则目录的相对路径
        """
        if rules_dir == "":
            rules_dir = FileManager.rules_dir
        # 缓存命中：该目录已加载过
        cached = getattr(self, "_loaded_dirs", set())
        if rules_dir in cached and self.rules:
            return self.rules
        rules_dict = FileManager.load_all_toml(rules_dir)
        if not rules_dict:
            # 空目录不是错误（如 ext 目录迁移后），返回空
            return self.rules
        # 解析 peek 引用（加载期，不影响运行期隔离）
        rules_dict = self._resolve_peek(rules_dict)
        for rule_name, rule_dict in rules_dict.items():
            if rule_name == "file_rules":
                continue
            rule = GrammarRule(rule_name, **rule_dict)  # 解包字典
            self.rules[rule_name] = rule
        self._loaded_dirs = cached | {rules_dir}
        return self.rules

    def rules_registration_from_file(self, file_path: str) -> dict[str, GrammarRule]:
        """从单个 TOML 文件加载规则。"""
        import tomllib

        with open(file_path, "rb") as f:
            rules_dict = tomllib.load(f)
        result = {}
        for rule_name, rule_dict in rules_dict.items():
            if rule_name == "file_rules":
                continue
            rule = GrammarRule(rule_name, **rule_dict)
            self.rules[rule_name] = rule
            result[rule_name] = rule
        return result
