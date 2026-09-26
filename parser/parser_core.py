"""Main parser — recursive descent with backtracking.

Orchestrates parsing by coordinating:
    - _production: production element dispatch + matching + end_case
    - attribute_binder: $N path extraction and node assembly
    - block_parser: block/body parsing
    - pratt_parser: Pratt expression parsing (独立库模块)
Doc: docs/language_walkthrough.md（Parser 主引擎：递归下降+回溯）
    - rule_selector: 规则选择 + production 分析 (独立库模块)"""

import sys
from typing import Any
from core.define import (
    Node,
    Token,
    GrammarRule,
    GrammarRulesRegister,
    FileManager,
    ParseError,
)
from core.config_registry import declare_cfg
from core.errors import ConfigError
from ._constants import ROOT_RULE_NAME

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# parser.operator_defs
#   #sym:config = [operator]
#   格式: dict — 运算符优先级定义
_operator_defs_cfg = declare_cfg("parser.operator_defs", [], __name__, "_operator_defs_cfg")

# parser.token_categories
#   #sym:config = [token_category]
#   格式: dict — Token 分类映射
_token_categories_cfg: dict = declare_cfg("parser.token_categories", {}, __name__, "_token_categories_cfg")

# parser.skip_types
#   格式: list[str] — 解析时需要跳过的空白/折叠 token 类型
#   默认值 ["newline", "space.fold"] 是引擎 token 协议的产物（lexer 产出的
#   空白类型，所有语言通用），语言包可不显式声明；有特殊跳过需求时可覆盖。
_skip_types_cfg: list[str] = declare_cfg(
    "parser.skip_types", ["newline", "space.fold"], __name__, "_skip_types_cfg"
)

# merged inline: ParseContext


class ParseContext:
    """解析上下文，管理解析过程中的所有状态"""

    def __init__(self, tokens: list[Token]) -> None:
        self._snapshot_stack = []
        self.tokens = tokens
        self.token_pointer = 0
        self.match_length = 0
        self.current_node: Node | None = None
        self.current_rule: GrammarRule | None = None
        self.production_pointer = 0
        # 当前规则匹配的起始 token 下标（match_productions 入口登记）——
        # 供「注释前 token 是否属本规则匹配范围」判据用（表达式注释让位闸门）
        self.production_start_ptr = 0
        self.exc_type = None
        self.exc_tb = None

        # 语义路径跟踪
        self.sibling_counter: dict[str, int] = {}  # 规则名 → 自然序
        self.path_stack: list[str] = []  # 当前语义路径栈

    def __enter__(self):
        # 进入 with 块时自动创建快照，异常时自动回滚
        snapshot = self.create_snapshot()
        self._snapshot_stack.append(snapshot)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        del exc_val, exc_tb  # context manager 协议签名参数，本实现不消费
        if not self._snapshot_stack:
            return False
        snapshot = self._snapshot_stack.pop()
        if exc_type is not None:
            self.restore_snapshot(snapshot)
        return False  # 异常继续传播

    def advance_token(self, count=1):
        self.token_pointer += count
        self.match_length += count

    def create_snapshot(self):
        """创建解析状态快照，用于回溯（tuple 比 dict 快 3x）"""
        return (
            self.token_pointer,
            self.match_length,
            self.current_node,
            self.current_rule,
            self.production_pointer,
            self.production_start_ptr,
        )

    def restore_snapshot(self, snapshot):
        (self.token_pointer,
         self.match_length,
         self.current_node,
         self.current_rule,
         self.production_pointer,
         self.production_start_ptr) = snapshot

    def update_current_node(self, node: Node | None) -> None:
        # current_node 允许 None（畸形输入恢复 old_node 可为 None——
        # fuzz 修复，见 _production.py try_block_rule 失败路径注释）
        self.current_node = node

    def update_current_rule(self, rule: GrammarRule) -> None:
        self.current_rule = rule

    def has_more_tokens(self) -> bool:
        return self.token_pointer < len(self.tokens)

    def peek_token(self, offset=0) -> Token | None:
        """查看指定偏移的token（不移动指针）"""
        pos = self.token_pointer + offset
        return self.tokens[pos] if pos < len(self.tokens) else None


class _ScopeEntry:
    """作用域条目"""

    def __init__(self, name: str, kind: str):
        self.name: str = name
        self.kind: str = kind
        # 本作用域中注册的符号
        self.symbols: dict[str, str] = {}


class _ScopeStack:
    """轻量级作用域栈，供 Parser 在解析过程中实时查询符号。

    与 Analyzer 的后阶段全量分析不同，_ScopeStack 只服务于 Parser 规则选择，
    回溯时需配合 snapshot/restore 回滚。

    scope 声明来源：规则 TOML 中的 [RuleName.analyzer] scope = { ... }。
    """

    def __init__(self) -> None:
        # 根作用域（全局）
        self._stack: list[_ScopeEntry] = [_ScopeEntry("__global__", "global")]

    # ── 快照/恢复（配合 parser 回溯） ──

    def snapshot(self) -> int:
        """返回当前栈深度作为快照。"""
        return len(self._stack)

    def restore(self, depth: int) -> None:
        """恢复到指定栈深度（丢弃上层作用域）。"""
        while len(self._stack) > depth:
            self._stack.pop()

    # ── 作用域管理 ──

    def push(self, name: str, kind: str) -> None:
        self._stack.append(_ScopeEntry(name, kind))

    def pop(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()

    # ── 符号注册与查找 ──

    def register(self, name: str, kind: str) -> None:
        self._stack[-1].symbols[name] = kind

    def lookup(self, name: str) -> str | None:
        """沿作用域链查找符号，返回其 kind，未找到返回 None。"""
        for entry in reversed(self._stack):
            if name in entry.symbols:
                return entry.symbols[name]
        return None

    # ── 查询 ──

    @property
    def depth(self) -> int:
        return len(self._stack)

    @property
    def current(self) -> _ScopeEntry:
        return self._stack[-1]

    def dump(self) -> list[dict]:
        """调试用：导出整个栈。"""
        return [
            {"name": e.name, "kind": e.kind, "symbols": dict(e.symbols)}
            for e in self._stack
        ]


def _atom_parser_impl(self, _tokens, idx, context):
    """atom_parser 的实际实现（独立函数避免每次 try_pratt_rule 创建闭包）"""
    del _tokens  # atom_parser 回调协议签名参数 (tokens, idx)，本实现只用 idx/context
    old_ptr = context.token_pointer
    context.token_pointer = idx
    start_ptr = context.token_pointer
    # 最长匹配（2026-08-28，层次化引用交错形态）：原子候选按 production
    # 长度降序尝试，取**消费最多**者——`a[0].b` 时 SelectExpr（吃 a[0]）
    # 有进展但残留 `.b`，HierExpr（吃 a[0].b）更长胜出；`a[0]` 纯下标两
    # 者等长，先试的 SelectExpr 胜（等长取先，AST 形状稳定）。原"第一个
    # 有进展即返回"使 SelectExpr 先命中 → 交错形态残留 token 致语句失败。
    best_node = None
    best_consumed = 0
    for rule in self.atomic_rules:
        snapshot = context.create_snapshot()
        node = self._try_rule_productions(context, rule)
        consumed = context.token_pointer - start_ptr
        if node is not None and consumed > best_consumed:
            best_node = node
            best_consumed = consumed
        context.restore_snapshot(snapshot)
    context.token_pointer = old_ptr
    if best_node is None:
        # 宏通配（引擎协议）：非空体宏调用出现在**原子位**时当作一个
        # 原子（宏节点）——语言包零宏知识（不声明任何槽位），合法性由 linter
        # 的真展开检查兜底。空体宏已由占位阶段改为 trivia。
        from core.define import Node
        from core.token_protocol import MACRO_CALL_TOKEN_TYPE, TRIVIA_TOKEN_TYPES

        toks = context.tokens
        j = start_ptr
        while j < len(toks) and toks[j].type in TRIVIA_TOKEN_TYPES:
            j += 1
        if j < len(toks) and toks[j].type == MACRO_CALL_TOKEN_TYPE:
            tok = toks[j]
            node = Node("MacroCall", content=tok.content)
            # 元数据走 add_attr（Node 的动态属性惯例；直接 setattr 会被静态
            # 检查判为未知属性赋值）
            node.add_attr("_macro_source_text", tok.content)
            node.add_attr("_macro_name", str(tok.content).lstrip("`").split("(")[0])
            node.add_attr("_tok_span", (j, j + 1))
            # consumed 从 idx 起算（含跳过的 trivia），与 pratt 的
            # `idx += consumed` 推进约定一致。
            return node, j + 1 - start_ptr
        return None, 0
    return best_node, best_consumed


def try_pratt_rule(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """使用 Pratt 解析器解析表达式规则"""
    if not context.has_more_tokens():
        return None

    start = context.token_pointer
    # 实验：stop_tokens 是否冗余（pratt 中缀循环对非运算符本来就会 break）
    stop_tokens = None
    # 入口优先级上限：语言包按规则声明 `pratt_level = "unary"`（不吃中缀）；
    # 非法值 fail-fast，不静默降级成默认层级（否则操作数会吞掉中缀运算符）。
    # ⚠ 未声明时字段默认值是 False（`GrammarRule._set_field_defaults` 的非列表字段
    #   缺省）——故 falsy 一律按 "expression" 处理，只有显式字符串才校验。
    level = getattr(rule, "pratt_level", None) or "expression"
    if level not in ("expression", "unary"):
        raise ConfigError(
            f"规则 {rule.name!r} 的 [parser] pratt_level 取值非法：{level!r}"
            "（允许 \"expression\"（默认，吃全部中缀）/ \"unary\"（只到一元层级））"
        )

    try:
        ast_node, consumed = pratt_parser.parse_with_count(
            context.tokens,
            start,
            self.operator_defs,
            atom_parser=lambda t, i: _atom_parser_impl(self, t, i, context),
            stop_tokens=stop_tokens,
            level=level,
            # 前缀位置跳过的行内注释（`a + /* c */ b`）经 sink 记录（P1.5
            # 修复 pratt 吞注释；ADR-0013 阶段 A 后 operator 间隙注释已挂
            # 节点 inline_after，sink 仅收无 operator 上下文的残余前缀注释）。
            comment_sink=lambda c: self._record_anchor(c, "inline"),
        )
    except ValueError as e:
        self._record_fail_site(context, rule=rule.name, reason=f"pratt: {e}")
        self._log_state(f"Pratt 解析: 不适合作为表达式 - {e}")
        return None
    except Exception as e:
        self._record_fail_site(context, rule=rule.name, reason=f"pratt: {e}")
        self._log_state(f"Pratt 解析失败: {e}")
        self._warn(f"Pratt 表达式解析失败: {e}")
        return None

    if ast_node is None or consumed == 0:
        self._log_state("Pratt 解析: 未消费任何 token")
        return None

    context.token_pointer = start + consumed
    self._log_state(f"Pratt 解析成功，消耗 {consumed} 个 token")
    return ast_node


from .rule_selector import RuleSelector
import parser.pratt_parser as pratt_parser

# 导入拆分后的模块方法
from .attribute_binder import (
    bind_attributes,
    try_inline_rule,
)
from ._production import (
    process_production_node,
    match_productions,
    rule_frame,
    try_block_rule,
    try_plain_rule,
    try_rule_productions,
    prepare_production,
    check_end_case,
    parse_token,
    parse_call,
    parse_seq,
    parse_choice,
    parse_repeat,
    parse_optional,
    parse_plus,
    repeat_loop,
    collect_following_comments,
)

from .block_parser import (
    parse_sentence,
    resolve_block_rule,
    consume_start_token,
    parse_block_body,
    parse_block,
    collect_line_comments,
)


class Parser:
    """语法分析器 — 将 token 流解析为 AST"""

    # 动态挂载属性：wrap 等消费方现场挂 lexer 供超宽行解析（见 pipeline.format_generated）
    lexer: Any = None

    # 调试日志文件（FileManager.debug_log_file 非空时在 __init__ 设置；类级
    # 默认 None 供静态检查，未设置时读取返回 None）
    debug_log_file: str | None = None

    # 日志级别（阈值 _log_level 过滤低级别调用）
    LOG_TRACE = -1
    LOG_DEBUG = 0
    LOG_INFO = 1
    LOG_WARN = 2
    LOG_ERROR = 3

    # ── 从拆分模块导入的方法绑定 ──
    # attribute_binder
    _bind_attributes = bind_attributes
    _try_inline_rule = try_inline_rule

    # _production (合并 rule_matcher + node_parsers)
    _parse_token = parse_token
    _collect_following_comments = collect_following_comments
    _parse_call = parse_call
    _parse_seq = parse_seq
    _parse_choice = parse_choice
    _parse_repeat = parse_repeat
    _parse_optional = parse_optional
    _parse_plus = parse_plus
    _repeat_loop = repeat_loop
    _process_production_node = process_production_node
    _match_productions = match_productions
    _try_rule_productions = try_rule_productions
    _rule_frame = rule_frame
    _try_block_rule = try_block_rule
    _try_plain_rule = try_plain_rule
    _prepare_production = prepare_production
    _check_end_case = check_end_case

    # atom_parser
    _try_pratt_rule = try_pratt_rule

    # block_parser
    parse_sentence = parse_sentence
    _resolve_block_rule = resolve_block_rule
    _consume_start_token = consume_start_token
    _parse_block_body = parse_block_body
    parse_block = parse_block
    _collect_line_comments = collect_line_comments

    def __init__(
        self,
        rules_dir: str | None = None,
        verbose: bool = False,
        log_file: str | None = None,
        pre_symbols: dict[str, str] | None = None,
        rules: dict[str, GrammarRule] | None = None,
        rule_selector: "RuleSelector | None" = None,
        silent: bool = False,
    ) -> None:
        """初始化解析器（分阶段装配，各段见 `_init_*` 方法）。

        Args:
            rules_dir: 语法规则目录（相对路径）。传入时由调用方接管 RuleSelector。
            verbose: 调试日志开关。True 时输出所有级别日志，False 时只输出 WARN/ERROR。
            log_file: 日志文件路径。None 时读 FileManager.debug_log_file，
                        空字符串或 "/dev/null" 类似值表示不写日志。
            pre_symbols: Lexer 预扫描符号表 { name: kind }，用于辅助规则选择。
            rules: 预加载的语法规则表。传入时跳过内部 GrammarRulesRegister 加载。
            rule_selector: 预构建的 RuleSelector。传入时跳过内部创建。
        """
        self._init_flags(verbose, silent, pre_symbols)
        self._load_brackets()
        self._init_rules(rules)
        self._init_logging(log_file)
        self.statement_rule_names = [
            name
            for name, rule in self.grammar_rules.items()
            if hasattr(rule, "has_pass_end_case") and rule.has_pass_end_case()
        ]
        self._init_pratt_language()
        self._init_rule_selector(rules_dir, rule_selector)
        self._init_skip_types()
        # 停点/trace 过滤器（set_trace 设置，按规则名或 token 位置）
        self._trace_rule: str | None = None
        self._trace_token_pos: int | None = None

        self._init_atoms()
        self._init_follows()
        self._init_anchors()

    def _init_flags(
        self, verbose: bool, silent: bool, pre_symbols: dict[str, str] | None
    ) -> None:
        """开关与容器字段。"""
        self.verbose = verbose
        # silent：探测性解析（宏体形态分类/提取等）全静默——不输出 WARN/失败报告，
        # 避免污染宿主解析流程的日志与门禁断言（真实语料无 WARN 断言）。
        self.silent = silent
        # 失败现场：token_index → {rule, reason, path}（按位置聚合，有界）
        self._fail_sites: dict[int, dict] = {}
        # 最近一次失败现场报告（退出前保留，供测试/程序化访问）
        self._last_failure_report: dict | None = None
        # 解析是否提前停止（输入未耗尽但无规则可继续）
        self._parse_truncated = False
        # 预扫描符号表（可选）
        self.pre_symbols = pre_symbols or {}
        self.pre_hints: dict[str, list[str]] = {}
        # 解析时作用域栈（可选，配合 peek scope 使用）
        self.scope_stack = _ScopeStack()

    def _load_brackets(self) -> None:
        """加载括号映射（配置驱动，命名逻辑集中在 core/utils.py）。"""
        from core.utils import get_bracket_map

        self._bracket_map, self._inverse_bracket_map = get_bracket_map()

    def _init_rules(self, rules: dict[str, GrammarRule] | None) -> None:
        """规则加载：外部注入优先，回退内部自动加载（不可得 → fail-fast）。"""
        self.grammar_rules: dict[str, GrammarRule] = {}
        if rules is not None:
            self.grammar_rules = rules
            return
        try:
            self.grammar_rules = (
                GrammarRulesRegister.get_default().rules_registration()
            )
        except FileNotFoundError as exc:
            # 无注入规则且默认语言包不可得 → 空规则表的 Parser 什么都解析
            # 不了（后续只会报"无规则可继续"），属配置/状态错，fail-fast
            # 报出原因（与 core/config_lifecycle.md「fail-fast」一致）。
            raise ConfigError(
                "[parser] 既无注入语法规则（rules=）也无可用默认语言包："
                f"请先加载语言包（ConfigRegistry.load_all）或显式传入 rules（{exc}）"
            ) from exc

    def _init_logging(self, log_file: str | None) -> None:
        """日志文件（构造参数优先，回退 FileManager 全局配置）与级别阈值。"""
        if log_file is None:
            if FileManager.debug_log_file is not None:
                self.debug_log_file = FileManager.get_full_path(
                    FileManager.debug_log_file
                )
        elif log_file:
            self.debug_log_file = FileManager.get_full_path(log_file)
        # log_file="" 或 "/dev/null" → 不写日志（不设置 self.debug_log_file）
        # 日志级别阈值：无文件且非 verbose → 只留 WARN+（stderr 可见），
        # 修复旧实现把 _log_state 整体替换为空 lambda 导致 WARN 也被吞的问题。
        # verbose → 全级别（TRACE 起）；有日志文件 → INFO 起写文件。
        if self.silent:
            self._log_level = self.LOG_ERROR + 1
        elif getattr(self, "debug_log_file", None) is None and not self.verbose:
            self._log_level = self.LOG_WARN
        elif self.verbose:
            self._log_level = self.LOG_TRACE
        else:
            self._log_level = self.LOG_INFO

    def _init_pratt_language(self) -> None:
        """pratt 侧语言装配：运算符表 / token 分类器。"""
        self.operator_defs = pratt_parser.process_operator_data(_operator_defs_cfg)
        if _token_categories_cfg:
            pratt_parser.install_token_classifier(_token_categories_cfg)

    def _init_rule_selector(
        self, rules_dir: str | None, rule_selector: "RuleSelector | None"
    ) -> None:
        """RuleSelector：外部注入优先；传 rules_dir 时由调用方接管（不建）。"""
        if rule_selector is not None:
            self.rule_selector = rule_selector
        elif rules_dir:
            pass
        else:
            self.rule_selector = RuleSelector(
                self.grammar_rules,
                self.statement_rule_names,
            )

    def _init_skip_types(self) -> None:
        """跳过 token 类型 = 语言配置 + 引擎协议占位 token。"""
        self.skip_types = list(_skip_types_cfg)
        # 引擎协议 trivia 恒定跳过：宏占位 token（空体宏展开为空的"跳过/占位"
        # 形态）不是语言知识——它由引擎协议产生（占位阶段），
        # 因此不放进语言配置 skip_types，而在引擎侧统一追加。
        from core.token_protocol import PLACEHOLDER_TOKEN_TYPE

        if PLACEHOLDER_TOKEN_TYPE not in self.skip_types:
            self.skip_types.append(PLACEHOLDER_TOKEN_TYPE)

    def _init_atoms(self) -> None:
        """原子规则表 + 内置前缀兜底节点名注入 pratt。

        A2：内置前缀兜底节点名与语言包规则名对齐——从"单字面 token production"
        的 is_atom 规则推导 {token_type: 规则名} 注入 pratt（如 literal.string →
        StringLiteral / StringLit，id → Identifier）。语言定义原子规则即自动对齐，
        无对应规则时 pratt 回退内置名（纯兜底）。
        """
        self.atomic_rules: list[GrammarRule] = sorted(
            (
                rule
                for rule in self.grammar_rules.values()
                if getattr(rule, "is_atom", False)
            ),
            key=lambda r: len(r.prods),
            reverse=True,
        )
        _atom_names: dict[str, str] = {}
        for _rule in self.atomic_rules:
            _prods = _rule.prods or []
            if (
                len(_prods) == 1
                and isinstance(_prods[0], str)
                and not _prods[0].startswith("@")
            ):
                _atom_names.setdefault(_prods[0], _rule.name)
        pratt_parser.install_atom_name_map(_atom_names)

    def _init_follows(self) -> None:
        """FOLLOW 集派生缓存（parser/follow.py）：check_end_case 的硬性依据。

        pratt 运算符成员从 token_category 的 operator 分类读取（语言数据，
        前缀成员如 "symbol.base."），注入 is_atom 规则的 FOLLOW。
        """
        _op_cfg = (
            _token_categories_cfg.get("operator", {})
            if isinstance(_token_categories_cfg, dict)
            else {}
        )
        _op_members = (
            list(_op_cfg.get("types", []) or []) if isinstance(_op_cfg, dict) else []
        )
        from .follow import compute_follows

        self._follows = compute_follows(self.grammar_rules, _op_members)

    def _init_anchors(self) -> None:
        """注释锚点容器与去重集（inline / line 两通道各自独立）。

        inline comment 锚点记录（restore 仅 tpc marker——普通注释进树，
        不再回插）；line comment 锚点（列表结构内被 production skip 吞掉的
        注释，restore 仅 tpc marker 通道）。
        去重（按通道分 key 空间）：parser 回溯会对同一注释重复进入收集点
        （候选规则逐一尝试、production 多次 skip），restore 端本就按
        (text, line) 去重保留首条——收集端同语义去重，消除冗余条目。
        两个锚点列表 restore 时各自独立去重，跨列表不去重（语义保等）。
        """
        self._comment_anchors: list[dict] = []
        self._line_comment_anchors: list[dict] = []
        self._anchor_seen_inline: set[tuple[str, int]] = set()
        self._anchor_seen_line: set[tuple[str, int]] = set()

    def _log_indent(self, context: ParseContext | None = None) -> str:
        """根据当前解析嵌套深度生成缩进前缀"""
        depth = 0
        if context is not None and hasattr(context, "path_stack"):
            depth = len(context.path_stack)
        return "  " * depth

    def _log_state(
        self,
        action: str,
        mode: str = "a",
        level: int = LOG_DEBUG,
        context: ParseContext | None = None,
    ) -> None:
        """带级别的日志记录。支持 action 为 callable 惰性求值。

        级别阈值 _log_level 过滤低级别调用（快速路径，避免空调用开销）；
        无日志文件时 WARN/ERROR 仍输出到 stderr（修复 WARN 被吞）。
        """
        # 快速路径：低于当前阈值级别直接跳过
        if level < getattr(self, "_log_level", self.LOG_INFO):
            return
        log_path = getattr(self, "debug_log_file", None)
        if log_path is None:
            # 无日志文件：WARN 输出到 stderr，其余跳过
            if level >= self.LOG_WARN:
                if callable(action):
                    action = action()
                print(f"[parser] {action}", file=sys.stderr)
            return

        if callable(action):
            action = action()
        if level >= self.LOG_INFO or self.verbose:
            indent = self._log_indent(context) if context else ""
            with open(log_path, mode, encoding="utf-8") as f:
                f.write(f"{indent}[{action}]\n")

    def _log_info(self, action: str, context: ParseContext | None = None) -> None:
        """INFO 级日志：始终输出"""
        self._log_state(action, level=self.LOG_INFO, context=context)

    def _warn(self, message: str, context: ParseContext | None = None) -> None:
        """WARN 级日志：由 _log_state 统一输出到日志文件和 stderr"""
        self._log_state(f"WARN: {message}", level=self.LOG_WARN, context=context)

    def set_trace(
        self, rule: str | None = None, token_pos: int | None = None
    ) -> None:
        """设置解析 trace 停点：按规则名或 token 位置过滤。

        命中条件时在 try_rule_productions 入口输出当前解析状态到 stderr
        （token_pointer / 当前 token / 语义路径）——适合观察某个规则或
        位置在回溯中的每次尝试，比逐层日志精准。
        """
        self._trace_rule = rule
        self._trace_token_pos = token_pos

    def _maybe_trace(self, context: ParseContext, rule: str = "") -> None:
        """命中 trace 停点条件时输出当前解析状态（stderr，ASCII）。"""
        if self._trace_rule is None and self._trace_token_pos is None:
            return
        hit_rule = (
            self._trace_rule is not None and bool(rule) and self._trace_rule in rule
        )
        hit_pos = (
            self._trace_token_pos is not None
            and context.token_pointer == self._trace_token_pos
        )
        if not (hit_rule or hit_pos):
            return
        print(
            f"[trace] rule={rule or '?'} pos={context.token_pointer} "
            f"{self._debug_token_info(context)} "
            f"path={'/'.join(context.path_stack)}",
            file=sys.stderr,
        )

    @staticmethod
    def _debug_token_info(context: ParseContext) -> str:
        """返回当前 token 和 token_pointer 的调试信息字符串"""
        if context.has_more_tokens():
            tok = context.peek_token()
            assert isinstance(tok, Token)
            return f"tok='{tok.content}' type={tok.type} idx={context.token_pointer}"
        return f"tok=EOF idx={context.token_pointer}"

    def _skip_tokens(self, context: ParseContext, skip_types: tuple) -> None:
        while context.has_more_tokens():
            cur = context.peek_token()
            if cur and cur.type in skip_types:
                context.advance_token()
            else:
                break

    @staticmethod
    def _restore_current_node(old_node: Node | None, context: ParseContext) -> None:
        if old_node is None:
            context.current_node = None
        else:
            context.update_current_node(old_node)

    def _record_anchor(self, entry: dict, target: str = "inline") -> None:
        """锚点条目收集去重：按 (text, line) 只记首条。

        parser 回溯会对同一注释重复进入收集点（候选规则逐一尝试、production
        多次 skip、parse_token 双收集）——restore 端本就按 (text, line) 去重
        保留首条锚，收集端同语义去重消除冗余（real 语料实测 _line_comment_
        anchors 441→335、_comment_anchors 447→427，均为回溯重复）。

        target: "inline" → _comment_anchors；"line" → _line_comment_anchors。
        两个列表 restore 时各自独立去重，跨列表不去重（语义保等）。
        """
        key = (entry["text"], entry["line"])
        if target == "line":
            if key in self._anchor_seen_line:
                return
            self._anchor_seen_line.add(key)
            self._line_comment_anchors.append(entry)
        else:
            if key in self._anchor_seen_inline:
                return
            self._anchor_seen_inline.add(key)
            self._comment_anchors.append(entry)

    def _mark_comment_collected(self, text: str, line: int) -> None:
        """注释已成 Comment 节点（collect_line_comments 收走）——从 line
        通道消除该注释的冗余簿记：prepare_production 回溯可能已先吞进
        _line_comment_anchors（此时注释由 Comment 节点结构序承载，restore
        existing_lines 本会跳过——条目纯冗余），登记 seen 防后续重复 +
        移除已存在的条目。ADR-0013 单机制：注释进树后不再走时域回插。"""
        key = (text, line)
        self._anchor_seen_line.add(key)
        self._line_comment_anchors[:] = [
            e for e in self._line_comment_anchors if (e["text"], e["line"]) != key
        ]

    def parse(self, tokens: list[Token]) -> Node | None:
        """解析器的入口：token 流 → AST"""
        # 每次 parse 重置状态
        self._comment_anchors = []
        self._line_comment_anchors = []
        self._anchor_seen_inline = set()
        self._anchor_seen_line = set()
        # 行尾注释去重集合（collect_following_comments 惰性创建）——
        # 跨 parse 复用 Parser 时残留会误跳过同 (text,line) 注释
        self._trailing_seen = set()
        # repeat 迭代深度（B1.3 claim 协调，_repeat_loop 维护）——
        # 跨 parse 复用 Parser 时残留会误判 claim 上下文
        self._repeat_iter_depth = 0
        self._fail_sites = {}
        self._last_failure_report = None
        self._parse_truncated = False
        context = ParseContext(tokens)

        try:
            # 语义路径：根规则路径入栈（根块规则名从语法树自推导——
            # get_block_rule 优先匿名根块，回退第一个块规则；推导失败
            # 才用 ROOT_RULE_NAME 回退值）
            root_name = self.rule_selector.get_block_rule() or ROOT_RULE_NAME
            context.sibling_counter[root_name] = 1
            context.path_stack.append(f"{root_name}[0]")
            block_node = self.parse_block(context, start_token="")
            context.path_stack.pop()
            if block_node is None:
                self._dump_failure_report(
                    context, reason="parse produced no root block"
                )
            elif self._parse_truncated and self._last_failure_report is None:
                # 解析提前停止（输入未耗尽但无规则可继续）→ 也保留失败现场
                self._dump_failure_report(
                    context, reason="parse truncated (unconsumed tokens)"
                )
            return block_node if block_node else None

        except ParseError:
            # ParseError 已在抛出处打印了详细上下文
            self._dump_failure_report(context, reason="ParseError")
            raise
        except Exception as exc:
            self._log_info(f"解析异常: {exc} | token={context.token_pointer}")
            self._dump_failure_report(context, reason=f"exception: {exc}")
            raise

    def _record_fail_site(
        self,
        context: ParseContext,
        rule: str = "",
        reason: str = "",
        preserve: bool = False,
    ) -> None:
        """记录失败现场：按 token_index 聚合（每个位置保留最新一条）。

        回溯解析中内层失败是常态，此处只做 O(1) dict 写入，不做窗口
        格式化——完整报告（含 token 窗口）在最终失败时由
        _dump_failure_report 一次性生成。

        preserve=True 时若该位置已有记录则不覆盖——用于上层泛化记录
        （如 "sentence"）不覆盖下层更具体的记录（如候选规则名）。
        """
        pos = context.token_pointer
        if preserve and pos in self._fail_sites:
            return
        self._fail_sites[pos] = {
            "rule": rule,
            "reason": reason,
            "path": "/".join(context.path_stack),
        }

    def _dump_failure_report(
        self, context: ParseContext, reason: str = ""
    ) -> None:
        """输出失败现场报告：位置 + token 窗口 + 失败点信息（退出前保留）。

        只在"所有路径失效、即将放弃"时调用一次；报告同时存入
        _last_failure_report 供测试/程序化访问。
        """
        from core.debug_report import build_failure_report, render_failure_report

        pos = context.token_pointer
        site = self._fail_sites.get(pos)
        if site is None and self._fail_sites:
            # 失败位置无记录：回退到最近的失败现场
            nearest = min(self._fail_sites, key=lambda k: abs(k - pos))
            site = self._fail_sites[nearest]
        report = build_failure_report(
            position=pos,
            tokens=getattr(context, "tokens", None),
            reason=reason or (site or {}).get("reason", ""),
            rule=(site or {}).get("rule", ""),
            path=(site or {}).get("path", ""),
            extra={
                "match_length": context.match_length,
                "fail_sites": len(self._fail_sites),
            },
        )
        self._last_failure_report = report
        if not getattr(self, "silent", False):
            print(render_failure_report(report), file=sys.stderr)
