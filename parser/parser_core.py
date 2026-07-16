"""Main parser — recursive descent with backtracking.

Orchestrates parsing by coordinating:
    - _production: production element dispatch + matching + end_case
    - attribute_binder: $N path extraction and node assembly
    - block_parser: block/body parsing
    - pratt_parser: Pratt expression parsing (独立库模块)
    - rule_selector: 规则选择 + production 分析 (独立库模块)"""

import sys
from core.define import (
    Node,
    Token,
    GrammarRule,
    GrammarRulesRegister,
    FileManager,
    ParseError,
)

# merged inline: ParseContext


class ParseContext:
    """解析上下文，管理解析过程中的所有状态"""

    def __init__(self, tokens: list[Token]) -> None:
        self._snapshot_stack = []  # 添加快照栈
        self.tokens = tokens
        self.token_pointer = 0
        self.match_length = 0
        self.current_node: Node | None = None
        self.current_rule: GrammarRule | None = None
        self.production_pointer = 0
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
        if not self._snapshot_stack:
            return False
        snapshot = self._snapshot_stack.pop()
        if exc_type is not None:
            self.restore_snapshot(snapshot)
        return False  # 异常继续传播

    def advance_token(self, count=1):
        """向前移动token指针"""
        self.token_pointer += count
        self.match_length += count

    def advance_production(self, count=1):
        """向前移动产生式指针"""
        self.production_pointer += count

    def create_snapshot(self):
        """创建解析状态快照，用于回溯（tuple 比 dict 快 3x）"""
        return (
            self.token_pointer,
            self.match_length,
            self.current_node,
            self.current_rule,
            self.production_pointer,
        )

    def restore_snapshot(self, snapshot):
        """恢复到之前的解析状态"""
        (self.token_pointer,
         self.match_length,
         self.current_node,
         self.current_rule,
         self.production_pointer) = snapshot

    def update_current_node(self, node: Node) -> None:
        """更新当前正在构造的 AST 节点。"""
        self.current_node = node

    def update_current_rule(self, rule: GrammarRule) -> None:
        """更新当前正在匹配的语法规则。"""
        self.current_rule = rule

    def update_match_length(self, length: int) -> None:
        """更新已匹配的 token 数。"""
        self.match_length = length

    def has_more_tokens(self) -> bool:
        """判断是否还有未解析的token"""
        return self.token_pointer < len(self.tokens)

    def peek_token(self, offset=0) -> Token | None:
        """查看指定偏移的token（不移动指针）"""
        pos = self.token_pointer + offset
        return self.tokens[pos] if pos < len(self.tokens) else None

    def check_end_case(self, end_case: list[str]) -> bool:
        """检查当前 token 是否属于结束符集合（或已无更多 token）"""
        if not self.has_more_tokens():
            return True
        next_token = self.peek_token()
        if next_token is None:
            return True
        return next_token.type in end_case


class ScopeEntry:
    """作用域条目"""

    def __init__(self, name: str, kind: str):
        self.name: str = name
        self.kind: str = kind
        # 本作用域中注册的符号
        self.symbols: dict[str, str] = {}


class ScopeStack:
    """轻量级作用域栈，供 Parser 在解析过程中实时查询符号。

    与 Analyzer 的后阶段全量分析不同，ScopeStack 只服务于 Parser 规则选择，
    回溯时需配合 snapshot/restore 回滚。

    scope 声明来源：规则 TOML 中的 [RuleName.analyzer] scope = { ... }。
    """

    def __init__(self) -> None:
        # 根作用域（全局）
        self._stack: list[ScopeEntry] = [ScopeEntry("__global__", "global")]

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
        """进入新作用域。"""
        self._stack.append(ScopeEntry(name, kind))

    def pop(self) -> None:
        """退出当前作用域。"""
        if len(self._stack) > 1:
            self._stack.pop()

    # ── 符号注册与查找 ──

    def register(self, name: str, kind: str) -> None:
        """在当前作用域注册符号。"""
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
    def current(self) -> ScopeEntry:
        return self._stack[-1]

    def current_kind(self) -> str:
        return self._stack[-1].kind

    def dump(self) -> list[dict]:
        """调试用：导出整个栈。"""
        return [
            {"name": e.name, "kind": e.kind, "symbols": dict(e.symbols)}
            for e in self._stack
        ]


def _atom_parser_impl(self, _tokens, idx, context):
    """atom_parser 的实际实现（独立函数避免每次 try_pratt_rule 创建闭包）"""
    old_ptr = context.token_pointer
    context.token_pointer = idx
    start_ptr = context.token_pointer
    for rule in self.atomic_rules:
        snapshot = context.create_snapshot()
        node = self._try_rule_productions(context, rule)
        if node is not None:
            consumed = context.token_pointer - start_ptr
            context.token_pointer = old_ptr
            return node, consumed
        context.restore_snapshot(snapshot)
    context.token_pointer = old_ptr
    return None, 0


def try_pratt_rule(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """使用 Pratt 解析器解析表达式规则"""
    if not context.has_more_tokens():
        return None

    start = context.token_pointer
    stop_tokens = (
        set(getattr(rule, "end_case", [])) if getattr(rule, "end_case", None) else None
    )

    try:
        ast_node, consumed = pratt_parser.parse_with_count(
            context.tokens,
            start,
            self.operator_defs,
            atom_parser=lambda t, i: _atom_parser_impl(self, t, i, context),
            stop_tokens=stop_tokens,
        )
    except ValueError as e:
        self._log_state(f"Pratt 解析: 不适合作为表达式 - {e}")
        return None
    except Exception as e:
        self._log_state(f"Pratt 解析失败: {e}")
        self._warn(f"Pratt 表达式解析失败: {e}")
        return None

    if ast_node is None or consumed == 0:
        self._log_state("Pratt 解析: 未消费任何 token")
        return None

    context.token_pointer = start + consumed
    self._log_state(f"Pratt 解析成功，消耗 {consumed} 个 token")
    return ast_node


from .rule_selector import RuleSelector, _compute_start_tokens
import parser.pratt_parser as pratt_parser

# 导入拆分后的模块方法
from .attribute_binder import (
    bind_attributes,
    try_inline_rule,
)
from ._production import (
    process_production_node,
    match_productions,
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

    # 日志级别
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
        cache_enabled: bool = True,
        verbose: bool = False,
        log_file: str | None = None,
        pre_symbols: dict[str, str] | None = None,
        rules: dict[str, GrammarRule] | None = None,
        rule_selector: "RuleSelector | None" = None,
    ) -> None:
        """初始化解析器。

        Args:
            rules_dir: 语法规则目录（相对路径）。传入时由调用方接管 RuleSelector。
            cache_enabled: 是否启用磁盘缓存。
            verbose: 调试日志开关。True 时输出所有级别日志，False 时只输出 WARN/ERROR。
            log_file: 日志文件路径。None 时读 FileManager.debug_log_file，
                        空字符串或 "/dev/null" 类似值表示不写日志。
            pre_symbols: Lexer 预扫描符号表 { name: kind }，用于辅助规则选择。
            rules: 预加载的语法规则表。传入时跳过内部 GrammarRulesRegister 加载。
            rule_selector: 预构建的 RuleSelector。传入时跳过内部创建。
        """
        self.grammar_rules: dict[str, GrammarRule] = {}
        self._cache_enabled = cache_enabled
        self.verbose = verbose
        # 失败尝试摘要
        self._failure_attempts: list[dict] = []
        # 预扫描符号表（可选）
        self.pre_symbols = pre_symbols or {}
        self.pre_hints: dict[str, list[str]] = {}
        # 解析时作用域栈（可选，配合 peek scope 使用）
        self.scope_stack = ScopeStack()

        # 加载括号映射（配置驱动，命名逻辑集中在 core/utils.py）
        from core.utils import get_bracket_map
        self._bracket_map, self._inverse_bracket_map = get_bracket_map()

        # 规则加载：外部注入优先，回退内部自动加载
        if rules is not None:
            self.grammar_rules = rules
        else:
            try:
                self.grammar_rules = (
                    GrammarRulesRegister.get_default().rules_registration()
                )
            except FileNotFoundError:
                pass
        # 日志文件：构造参数优先，回退到 FileManager 全局配置
        if log_file is None:
            if FileManager.debug_log_file is not None:
                self.debug_log_file = FileManager.get_full_path(
                    FileManager.debug_log_file
                )
        elif log_file:
            self.debug_log_file = FileManager.get_full_path(log_file)
        # log_file="" 或 "/dev/null" → 不写日志（不设置 self.debug_log_file）
        self.statement_rule_names = [
            name
            for name, rule in self.grammar_rules.items()
            if hasattr(rule, "has_pass_end_case") and rule.has_pass_end_case()
        ]
        # 运算符定义（从 ConfigRegistry 获取）
        from core.config_registry import config as _cfg

        raw_ops = _cfg.get("pratt.operator_defs")
        self.operator_defs = pratt_parser.process_operator_data(raw_ops)
        # Token 分类器（ConfigRegistry 已加载）
        categories = _cfg.get("pratt.token_categories")
        if categories:
            pratt_parser.install_token_classifier(categories)
        # RuleSelector：外部注入优先，回退内部创建
        if rule_selector is not None:
            self.rule_selector = rule_selector
        elif rules_dir:
            pass
        else:
            self.rule_selector = RuleSelector(
                self.grammar_rules,
                self.statement_rule_names,
                cache_enabled=cache_enabled,
            )
        self.skip_types = ["newline", "space.fold"]

        # 无日志文件时替换 _log_state 为空操作，避免 28k+ 次空调用开销
        if getattr(self, "debug_log_file", None) is None and not self.verbose:
            self._log_state = lambda *a, **kw: None  # type: ignore[method-assign]

        self.atomic_rules: list[GrammarRule] = sorted(
            (
                rule
                for rule in self.grammar_rules.values()
                if getattr(rule, "is_atom", False)
            ),
            key=lambda r: len(r.prods),
            reverse=True,
        )
        # inline comment 锚点记录（渲染后通过锚点匹配回注）
        self._comment_anchors: list[dict] = []
        # line comment 锚点（列表结构内被 production skip 吞掉的注释，渲染后回插）
        self._line_comment_anchors: list[dict] = []

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
        """带级别的日志记录。支持 action 为 callable 惰性求值。"""
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

    @staticmethod
    def _debug_token_info(context: ParseContext) -> str:
        """返回当前 token 和 token_pointer 的调试信息字符串"""
        if context.has_more_tokens():
            tok = context.peek_token()
            assert isinstance(tok, Token)
            return f"tok='{tok.content}' type={tok.type} idx={context.token_pointer}"
        return f"tok=EOF idx={context.token_pointer}"

    def _expected_tokens_for_rule(self, rule: GrammarRule) -> str:
        """计算规则可能接受的起始 token 类型集合，返回可读描述。"""
        from .rule_selector import analyze_production_features

        prods = rule.prods
        if not prods:
            return "<empty production>"
        try:
            feat = analyze_production_features(prods[0])
        except Exception:
            return "<analyze failed>"
        if not feat:
            return "<no features>"
        visited: set = set()
        starts = _compute_start_tokens(feat, self.grammar_rules, visited)
        if not starts:
            return "<unknown>"
        sorted_starts = sorted(starts)
        if len(sorted_starts) > 10:
            return (
                f"{{{', '.join(sorted_starts[:10])}, ...}} ({len(sorted_starts)} total)"
            )
        return f"{{{', '.join(sorted_starts)}}}"

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

    def parse(self, tokens: list[Token]) -> Node | None:
        """解析器的入口：token 流 → AST"""
        # 每次 parse 重置状态
        self._comment_anchors = []
        self._line_comment_anchors = []
        self._failure_attempts = []
        context = ParseContext(tokens)

        try:
            # 语义路径：Root 规则路径入栈
            context.sibling_counter["Root"] = 1
            context.path_stack.append("Root[0]")
            block_node = self.parse_block(context, start_token="")
            context.path_stack.pop()
            if block_node is None:
                self._dump_failure_summary(context)
            return block_node if block_node else None

        except ParseError:
            # ParseError 已在抛出处打印了详细上下文
            self._dump_failure_summary(context)
            raise
        except Exception as exc:
            self._log_info(f"解析异常: {exc} | token={context.token_pointer}")
            self._dump_failure_summary(context)
            raise

    def _dump_failure_summary(self, context: ParseContext) -> None:
        """输出失败尝试摘要：列出所有尝试过的规则及对应 token 位置"""
        if not self._failure_attempts:
            return
        print("\n[parser] ═══ 失败尝试摘要 ═══", file=sys.stderr)
        print(f"[parser]  共 {len(self._failure_attempts)} 次尝试失败", file=sys.stderr)
        # 按 token_index 分组去重，只显示每个位置最后一次尝试的规则
        seen_pos: dict[int, list[str]] = {}
        for fa in self._failure_attempts:
            pos = fa.get("token_index", -1)
            seen_pos.setdefault(pos, []).append(fa.get("rule", "?"))
        for pos in sorted(seen_pos.keys()):
            rules = seen_pos[pos]
            # 去重规则名（同一个位置可能多次尝试同一条规则）
            unique_rules = list(dict.fromkeys(rules))
            print(
                f"[parser]  token_pos={pos}  rules={unique_rules}",
                file=sys.stderr,
            )
        print(
            f"[parser]  ═══ 当前 token: {context.token_pointer} ═══",
            file=sys.stderr,
        )
