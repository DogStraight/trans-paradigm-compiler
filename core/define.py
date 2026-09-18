"""Core type definitions: Token, GrammarRule, GrammarRulesRegister, Node.

These types are shared across all pipeline stages — Lexer produces Token,
Parser consumes Token and produces Node (AST), GrammarRule drives both
parsing and rendering.

Doc: linter/linter_architecture.md
"""

import json
import re
import tomllib
import os
from pathlib import Path

from core.errors import (
    ConfigError,
    GrammarError,
    LexError,
    ParseError,
    TransformError,
    LintInternalError,
)
from core.engine_compat import check_engine_compat

# 错误类 re-export：`from core.define import ParseError` 兼容（见 core/errors.py）
__all__ = [
    "ConfigError",
    "GrammarError",
    "LexError",
    "ParseError",
    "TransformError",
    "LintInternalError",
]

# ── 配置文件定位（单一实现在 core/_user_config.py，此处 re-export） ──
from core._user_config import find_user_config as _find_user_config


def _load_tpc_meta() -> dict:
    """加载项目配置。

    架构：
        tpc_config.json（用户配置）→ 选择语法包
            └── grammar/<rules_dir>/tpc.toml（语法包自带引擎接口配置）
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 步骤 1：加载用户配置，定位语法包
    user_config = _find_user_config()
    if user_config:
        try:
            with open(user_config, encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, KeyError) as e:
            raise ConfigError(f"[config] {user_config} parse failed: {e}")
    else:
        cfg = {}

    # 步骤 2：解析语法包路径
    # tpc_config.json 中 grammar 可以是字符串（路径）或旧格式对象
    grammar_val = cfg.get("grammar", "")
    if isinstance(grammar_val, str):
        grammar_dir = grammar_val
    elif isinstance(grammar_val, dict):
        grammar_dir = grammar_val.get("rules_dir", "")
    else:
        grammar_dir = ""
    # 用户配置缺失（wheel 安装后无项目 config/tpc_config.json）时回退默认语言包。
    # root 在 editable（项目根）与 wheel（site-packages）两种模式下都指向
    # grammar 包所在目录的父级，故 root/grammar/verilog 两种模式均可定位。
    if not grammar_dir:
        grammar_dir = "grammar/verilog"

    # 步骤 3：加载语法包 tpc.toml（引擎接口配置）
    meta_path = os.path.join(root, grammar_dir, "tpc.toml")
    meta: dict = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = tomllib.loads(f.read())
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"[config] {grammar_dir}/tpc.toml parse failed: {e}")
    # 引擎 API 兼容校验（[engine] 段，fail-fast；import 期即拦）
    check_engine_compat(meta, grammar_dir or meta_path)

    # 步骤 4：插件目录由 tpc.toml [plugins] enabled 管理（config_registry 自动发现）
    ext_dirs: list[str] = []

    # 步骤 5：归一化 — grammar 统一为对象格式
    merged = dict(cfg)
    merged["grammar"] = {
        "rules_dir": grammar_dir,
        "ext_dirs": ext_dirs,
    }
    # tpc.toml 中其他 engine config 补入（[engine] 已单独校验，不入配置）
    for k, v in meta.items():
        if k not in ("grammar", "engine"):
            merged.setdefault(k, v)

    if "grammar" not in merged:
        raise ConfigError(
            f"[config] No grammar package found.\n"
            f"  Create config/tpc_config.json or ensure {grammar_dir}/tpc.toml exists."
        )
    return merged


_tpc_meta = _load_tpc_meta()

# 增强语法层目录（来自 tpc.toml [grammar]）
DEFAULT_EXT_DIRS: list[str] = _tpc_meta["grammar"]["ext_dirs"]

# 核心语法规则目录（来自 tpc.toml [grammar]）
DEFAULT_RULES_DIR: str = _tpc_meta["grammar"]["rules_dir"]


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


# ── AST 字段名协议（引擎约定，单一事实源） ──────────────────────
# parser 产出 / normalizer 消费 / renderer 递归的字段名，集中在此：
#   CHILDREN_FIELD 子节点列表字段名（Node.add_sub_node / iter_children / renderer
#                  children_field 默认值 / normalizer 展平目标）
#   BODY_FIELD      块 body 字段名（语法 TOML node 绑定产出，normalizer 按布局
#                  role=flatten 展平进 CHILDREN_FIELD）
CHILDREN_FIELD = "sub_node"
BODY_FIELD = "body"


class Node:

    # ── 引擎元数据（可选，非语法结构；dump 过滤下划线前缀）──
    # 源位置：parser 规则节点创建时挂载（_production.py），语义诊断定位用；
    # 源文件：跨文件诊断 related 链定位（ProjectChecker 挂载）。
    _pos_line: int | None = None
    _pos_col: int | None = None
    _file: str | None = None
    # token 范围（半开 [start, end)，token 流索引）：parser 规则节点解析成功时
    # 挂载（_production.py），供增量重解析（P3.2）结构对齐定位；下划线前缀
    # = 引擎元数据，不进 dump/序列化（同 _pos_line）。
    _tok_span: tuple[int, int] | None = None
    # MacroCall 节点的宏调用原文（parser 从 `macro.call` token 内容挂载）：
    # 渲染按它直出原文，输出面走 raw 源区间（ADR-0016）。
    _macro_source_text: str | None = None

    # 子节点列表（CHILDREN_FIELD，见 add_sub_node / iter_children / renderer）
    sub_node: list["Node"]

    def __init__(self, node_name: str, **kwargs) -> None:
        self.node_name = node_name
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name: str):
        """属性未挂载时的友好报错（替代裸 AttributeError）。

        AST 节点属性由语法 TOML 的 node 绑定（如 cond = "$3"）挂载；
        访问不存在属性通常意味着：位置捕获匹配失败（slot 为空未挂载）、
        绑定属性名拼写错误、或 choice 分支形态差异。hasattr / getattr(obj,
        name, default) 语义不变（AttributeError 被正常捕获）。
        """
        existing = ", ".join(sorted(vars(self))) or "(none)"
        node_name = vars(self).get("node_name", "?")
        raise AttributeError(
            f"节点 {node_name!r} 没有属性 {name!r}（现有: {existing}）。"
            '若该属性来自语法 TOML 的 node 绑定（如 cond = "$3"），'
            "请检查对应位置捕获是否匹配失败（slot 为空未挂载）"
            "或绑定属性名拼写。"
        )

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
            # 下划线前缀 = 引擎内部元数据（如 _pos_line/_pos_col 源位置），
            # 不属于语法结构，不进序列化（避免污染 AST dump/快照）。
            if attr == "node_name" or attr.startswith("_") or value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            dumped = Node._dump_item(value)
            if dumped is not None:
                result[attr] = dumped
        return {self.node_name: result}

    def add_sub_node(self, sub: "Node") -> None:
        if not hasattr(self, CHILDREN_FIELD):
            setattr(self, CHILDREN_FIELD, [])
        getattr(self, CHILDREN_FIELD).append(sub)

    def iter_children(self):
        seen = set()
        if hasattr(self, CHILDREN_FIELD):
            seen.update(id(c) for c in getattr(self, CHILDREN_FIELD))
            yield from getattr(self, CHILDREN_FIELD)
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


# ── Node 树通用工具（引擎与语言包插件共用） ──

def iter_nodes(root: Node):
    """DFS 迭代整棵 AST（先根后子；含属性挂载的子节点）。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.iter_children():
            stack.append(child)


def unwrap_optional(node: Node | None) -> Node | None:
    """穿透 parser 的 optional 包装节点（内容在 sub_node[0]，可嵌套）。

    单元素可选项（`$N` 捕获可选组、inline 规则展平）在 AST 里可能留壳，
    消费端取值前统一穿透；非 optional 原样返回，穿透落空 → None。
    """
    while isinstance(node, Node) and node.node_name == "optional":
        sub = getattr(node, "sub_node", None) or []
        node = sub[0] if sub else None
    return node


def collect_nodes(root: Node, node_name: str) -> list[Node]:
    """某 `node_name` 的全部节点（先根序）。"""
    return [n for n in iter_nodes(root) if n.node_name == node_name]


class FileManager:
    """纯静态工具类 — 文件路径管理与 TOML 加载。全局单例（无实例状态）。"""

    _base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_file: str = ""
    rules_dir: str = DEFAULT_RULES_DIR
    lookup_file: str = ""
    cg_rules_dir: str = ""
    debug_log_file: str | None = None

    @classmethod
    def get_full_path(cls, relative_path: str) -> str:
        """相对项目根解析路径；绝对路径原样返回（规范化）。

        历史：曾对输入统一 lstrip("/") 再拼 _base_dir——绝对路径在 POSIX 上
        被剥掉前导 / 后当相对路径重复拼接（/workspace + workspace/grammar/...，
        Windows 因盘符绝对路径被 Path 替换才碰巧正确）。绝对路径必须原样透传。
        """
        if os.path.isabs(relative_path):
            return os.path.normpath(relative_path)
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
            # 跳过：下划线前缀（辅助文件）、token.toml（语言词法覆盖，
            # 由 [lexer] 声明加载）、tpc.toml（语言包配置入口，[lexer]/
            # [parser] 等段是配置声明非语法规则）、plugins（语言插件目录，
            # 插件 tpc.toml 不是语法规则——如 asm_gen 的 [transform] 表会
            # 污染规则集）
            if (
                fname.startswith("_")
                or fname == "token.toml"
                or fname == "tpc.toml"
                or fname == "plugins"
            ):
                continue
            fpath = os.path.join(dir_path, fname)
            # 子目录递归
            if os.path.isdir(fpath) and "." not in fname:
                # 插件声明式检查规则表目录（rules/）：[[checks]] 数组是
                # check_registry 数据（core/check_registry.py 加载），非语法
                # 规则——ext_dirs 直接指向 plugins/ 时（如 LinterScanner
                # ext_dirs=["grammar/verilog/plugins"]）递归扫到会把顶层
                # checks list 当规则表值加载（_resolve_peek 崩，2026-08-28
                # name_check 插件新增后暴露）。
                if fname == "rules":
                    continue
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


class GrammarRule:
    """语法规则

    由 TOML 文件加载，除标准的 production/node/exclude 外，
    可通过自声明属性附加语义角色，供下游消费（不限于 AnalysisTraversal）：

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
        "exclude",
        "inline",
        "pratt",
        "is_atom",
        "is_block",
        "is_statement",
    }
    # 默认值为列表的字段
    _LIST_FIELDS = {"production", "node", "exclude"}

    # ── 语法规则可选字段（TOML 动态挂载；类级注解供静态检查/IDE）──
    # is_statement — [Rule].is_statement = true：语句级规则标记
    # （linter 语句发现 / parser parse_sentence 候选，见 has_pass_end_case）
    is_statement: bool | None = None

    # 其余动态挂载字段（__init__ 经 setattr 从 kwargs/parser 阶段表提取；
    # 类级注解仅供静态检查/IDE，不建运行时类属性——运行时行为零变化）。
    production: list[str]
    node: dict
    exclude: list
    inline: bool
    pratt: bool
    is_atom: bool
    is_block: bool
    parser: dict
    analyzer: dict
    renderer: dict
    inject: dict
    transform: dict

    # node 绑定中 $N 位置捕获规约（用于静态越界校验）
    _RE_POS_REF = re.compile(r"^\$(\d+)(?:\.|$)")

    # ── 规则字段 schema（fail-fast 校验） ──────────────────────────
    # 顶层合法字段：引擎字段 + 语言包扩展点（inject/transform）+ 阶段子表。
    # 未知顶层字段（拼写错误/误放字段）→ GrammarError。
    _TOP_LEVEL_FIELDS = _KNOWN_FIELDS | {
        "inject",
        "transform",
        "parser",
        "analyzer",
        "renderer",
    }
    # 各阶段合法字段。analyzer 阶段**宽松**：scope/symbol/ref_collect/
    # identifier_ref/primitives 是引擎字段，其余是插件原语名（开放扩展点，
    # 如 check_name_call）——不严格校验未知字段。
    # parser 阶段含 scope：_resolve_peek 会把 analyzer.scope 拷贝到 parser
    # 顶层（peek = { scope = "analyzer" }），故 scope 是 parser 合法字段。
    _STAGE_FIELDS = {
        "parser": {"production", "node", "exclude", "peek", "inline", "is_atom", "pratt", "scope"},
        "renderer": {"layout", "head", "body", "tail", "override"},
    }
    # 布尔字段（类型校验）
    _BOOL_FIELDS = {"inline", "pratt", "is_atom", "is_block", "is_statement"}

    @classmethod
    def _validate_fields(cls, name: str, kwargs: dict) -> None:
        """规则字段 schema 校验（fail-fast）。

        拦截：未知顶层字段、未知 parser/renderer 阶段字段、布尔字段类型错。
        analyzer 阶段宽松（插件原语开放）。
        """
        unknown = set(kwargs) - cls._TOP_LEVEL_FIELDS
        if unknown:
            raise GrammarError(
                f"[grammar] 规则 {name} 含未知顶层字段 {sorted(unknown)}。"
                f"合法字段: {sorted(cls._TOP_LEVEL_FIELDS)}"
            )
        for stage in ("parser", "renderer"):
            stage_data = kwargs.get(stage)
            if not isinstance(stage_data, dict):
                continue
            unknown_stage = set(stage_data) - cls._STAGE_FIELDS[stage]
            if unknown_stage:
                raise GrammarError(
                    f"[grammar] 规则 {name} 的 [{stage}] 含未知字段 {sorted(unknown_stage)}。"
                    f"合法字段: {sorted(cls._STAGE_FIELDS[stage])}"
                )
        for fld in cls._BOOL_FIELDS:
            if fld in kwargs and not isinstance(kwargs[fld], bool):
                raise GrammarError(
                    f"[grammar] 规则 {name} 的 {fld} 必须是布尔值，"
                    f"got {type(kwargs[fld]).__name__}"
                )
            for stage in ("parser", "analyzer", "renderer"):
                sd = kwargs.get(stage)
                if isinstance(sd, dict) and fld in sd and not isinstance(sd[fld], bool):
                    raise GrammarError(
                        f"[grammar] 规则 {name} 的 [{stage}].{fld} 必须是布尔值，"
                        f"got {type(sd[fld]).__name__}"
                    )

        cls._validate_node_specs(name, kwargs)

    @classmethod
    def _validate_node_specs(cls, name: str, kwargs: dict) -> None:
        """node 绑定中 $N 位置捕获的静态越界校验（fail-fast，对齐 ADR-0003）。

        拦截：$N 越界（N > production 顶层 slot 数）→ GrammarError。
        块规则的 production 已剥离首尾字面 token（parser 块路径单独消费
        起止符，绑定基于剥离后的内容部分编号，见 __init__），校验使用
        同一剥离逻辑。
        不拦截：$N.path 子路径的属性存在性——choice 分支形态差异（同一
        slot 不同分支挂载不同属性）是设计语义，运行时由 Node.__getattr__
        给出友好报错 + attribute_binder 诊断。
        """
        parser_data = kwargs.get("parser")
        node_map = parser_data.get("node") if isinstance(parser_data, dict) else None
        if not isinstance(node_map, dict) or not node_map:
            return
        raw_prods = parser_data.get("production") if isinstance(parser_data, dict) else None
        if not isinstance(raw_prods, list):
            return
        prods = list(raw_prods)
        is_block = kwargs.get("is_block") is True or bool(
            isinstance(parser_data, dict) and parser_data.get("is_block") is True
        )
        if is_block:
            if prods and isinstance(prods[0], str) and not prods[0].startswith("@"):
                prods.pop(0)
            if prods and isinstance(prods[-1], str) and not prods[-1].startswith("@"):
                prods.pop()
        max_slot = len(prods)
        for attr, spec in node_map.items():
            for item in spec if isinstance(spec, list) else [spec]:
                if not isinstance(item, str):
                    continue
                m = cls._RE_POS_REF.match(item)
                if m is None:
                    continue
                idx = int(m.group(1))
                if not (1 <= idx <= max_slot):
                    raise GrammarError(
                        f"[grammar] 规则 {name} 的 node 绑定 {attr} = {item!r} 越界："
                        f"production 共 {max_slot} 个 slot"
                        f"（块规则已剥离起止符），不存在 ${idx}。"
                    )

    def __init__(self, name: str, **kwargs):
        self.name = name

        # 规则字段 schema 校验（fail-fast）
        self._validate_fields(name, kwargs)

        self._set_field_defaults()
        self._apply_stage_overrides(kwargs)

        # 剩余未识别的属性
        for key, value in kwargs.items():
            setattr(self, key, value)

        self._derive_block_bounds()

    def _set_field_defaults(self) -> None:
        """未显式声明的字段取缺省：列表字段 []，其余 False。"""
        for fld in self._KNOWN_FIELDS:
            if fld in self._LIST_FIELDS:
                setattr(self, fld, [])
            else:
                setattr(self, fld, False)

    def _apply_stage_overrides(self, kwargs: dict) -> None:
        """嵌套阶段结构（parser / analyzer / renderer）的属性提到顶层。

        同时**保留**原始嵌套（`self.parser = {...}` 等）——阶段块整体与拆出的
        顶层字段并存，消费方按需取用。
        """
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

    @staticmethod
    def _is_literal_token(p) -> bool:
        """是否纯字面 token（非 `@` 引用、不含组语法字符）。

        组/可选/重复字符串（如 `"(symbol.base.colon,@Identifier)?"`）不是块边界。
        """
        return (
            isinstance(p, str)
            and not p.startswith("@")
            and not any(ch in p for ch in "()|,*+?")
        )

    def _derive_block_bounds(self) -> None:
        """is_block 块规则：从 production 首尾**字面 token** 推导
        block_start / block_end 与 block_prods（内容部分）。

        方案 B：production 保留完整（生产式即真相，作者可读全形），不再剥离——
        block_prods 存"内容部分"（去首尾）供块路径/linter/FOLLOW 匹配块头使用，
        node 绑定基于完整 production 编号（$1 = block_start）。
          production = ["keyword.module", "@Identifier", ..., "keyword.endmodule"]
          → block_start="keyword.module", block_end="keyword.endmodule",
            block_prods=["@Identifier", ...]（内容部分）

        块起止符判定语言无关：任何非 `@` 字面 token 都可作块边界（原实现硬编码
        `keyword.` 前缀是 Verilog 渗透——module/begin/end 都是 keyword；c4 的
        `{`/`}`（bracket）无法推导导致匿名块无限递归）。
        """
        self.block_start = ""
        self.block_end = ""
        self.block_prods: list = []
        if not (getattr(self, "is_block", False) and self.prods):
            return
        prods = list(self.prods)
        if prods and self._is_literal_token(prods[0]):
            self.block_start = prods[0]
        if prods and self._is_literal_token(prods[-1]):
            self.block_end = prods[-1]
        elif prods:
            # 尾元素是组/可选组（如 UDP 的 endprimitive 后接可选的
            # ": name" 结尾标签——尾元素 "(colon,id)?"）→ 向前取最后一
            # 个纯字面 token 作 block_end（标准块尾前可有可选标签）。
            for p in reversed(prods[:-1]):
                if self._is_literal_token(p):
                    self.block_end = p
                    break
        # 内容部分（去首尾字面 token）
        self.block_prods = list(prods)
        if self.block_start:
            self.block_prods = self.block_prods[1:]
        if self.block_end:
            # block_end 可能不在尾元素（如 UDP 的 endprimitive 后接可选
            # ": name" 标签——block_end 回退推导到倒数第二）→ 剥到
            # block_end 元素之前（而非固定 -1，否则 block_end 残留进
            # 块头被 match_productions 消费，块体循环吞掉后续兄弟块）。
            idx = len(self.block_prods) - 1
            while idx >= 0 and self.block_prods[idx] != self.block_end:
                idx -= 1
            self.block_prods = self.block_prods[:idx]

    def has_pass_end_case(self) -> bool:
        """该规则是否为语句级规则（用于 parse_sentence 候选列表）。

        is_statement=True → 是语句规则，加入候选列表。
        is_statement=False → 非语句规则，排除。
        """
        return self.is_statement is True

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
        # 语言包归属（相对路径已规范化）：语言切换 = 重建（见 begin_language）
        self._source_dir: str | None = None

    def reset(self) -> None:
        """清空规则表与目录缓存（语言切换 = 重建，见 begin_language）。"""
        self.rules.clear()
        self._loaded_dirs.clear()

    def begin_language(self, rules_dir: str) -> None:
        """声明"接下来的注册属于哪个语言包"：与上次不同则先重置。

        默认单例跨语言只增不减会让后一语言的规则表混入前一语言规则，**且顺序
        靠前**——`RuleSelector.get_block_rule()` 取"第一个匿名块规则"，于是根
        规则被前一语言夺走（实测：同进程先跑 c4 再跑 verilog，verilog 源码被按
        c4 的 `Program` 解析 → 渲染输出为空）。语言切换 = 重建，才能落实
        "单语言选择模型"（切换语言 = 重新初始化管线）。
        """
        key = os.path.normcase(os.path.abspath(rules_dir)) if rules_dir else ""
        if self._source_dir != key:
            self.reset()
            self._source_dir = key

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
            if not isinstance(rule_dict, dict):
                # 非 dict 规则值（如顶层 list 数据被误并入——规则表/协议
                # 数据等）跳过，不参与 peek 解析（防御，2026-08-28）
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
                    raise GrammarError(
                        f"peek: rule '{rule_name}' source stage "
                        f"'{source_stage_name}' not found or not a dict"
                    )
                value = source_stage.get(target_field)
                if value is None:
                    raise GrammarError(
                        f"peek: rule '{rule_name}' field '{target_field}' "
                        f"not found in stage '{source_stage_name}'"
                    )
                parser[target_field] = copy.deepcopy(value)
        return rules_dict

    def rules_registration(self, rules_dir: str = "") -> dict[str, GrammarRule]:
        """加载语法规则：优先从目录加载所有 .toml 文件（递归，_ 前缀跳过）。

        目录不存在或为空：返回当前规则表，不报错（空目录不是错误，如 ext
        目录迁移后残留）。支持缓存：已加载过的目录跳过磁盘 IO。

        Args:
            rules_dir: 规则目录的相对路径（空串用 FileManager.rules_dir）。
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
