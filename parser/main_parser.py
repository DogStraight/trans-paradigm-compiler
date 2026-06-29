"""Main parser — recursive descent with backtracking.

Orchestrates parsing by coordinating sub-parsers:
  - node_parsers: token/call/seq/choice/repeat/optional
  - production_matcher: rule production matching
  - attribute_binder: $N path extraction and node assembly
  - block_parser: block/body parsing
  - atom_parser: atomic rule + Pratt expression
  - end_case_checker: terminating token validation
"""

import sys
from typing import Optional, List, Dict
from core.define import Node, Token, GrammarRule, GrammarRulesRegister, FileManager, ParseError
from .parser_context import ParseContext
from .rule_selector import RuleSelector, _compute_start_tokens
import parser.pratt_parser as pratt_parser

# 导入拆分后的模块方法
from .attribute_binder import (
    bind_attributes,
    try_inline_rule,
)
from .node_parsers import (
    parse_token,
    parse_call,
    parse_seq,
    parse_choice,
    parse_repeat,
    parse_optional,
    parse_plus,
    repeat_loop,
)
from .production_matcher import (
    process_production_node,
    match_productions,
    try_rule_productions,
)
from .end_case_checker import prepare_production, check_end_case
from .atom_parser import try_pratt_rule
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

    # node_parsers
    _parse_token = parse_token
    _parse_call = parse_call
    _parse_seq = parse_seq
    _parse_choice = parse_choice
    _parse_repeat = parse_repeat
    _parse_optional = parse_optional
    _parse_plus = parse_plus
    _repeat_loop = repeat_loop

    # production_matcher
    _process_production_node = process_production_node
    _match_productions = match_productions
    _try_rule_productions = try_rule_productions

    # end_case_checker
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
    ) -> None:
        self.grammar_rules: Dict[str, GrammarRule] = {}
        self._cache_enabled = cache_enabled
        self.verbose = verbose
        # 失败尝试摘要
        self._failure_attempts: list[dict] = []

        try:
            self.grammar_rules = GrammarRulesRegister().rules_registration()
        except FileNotFoundError:
            pass
        if FileManager.debug_log_file is not None:
            self.debug_log_file = FileManager.get_full_path(FileManager.debug_log_file)
        if rules_dir:
            self.operator_defs = pratt_parser.load_operator_defs(rules_dir)
        self.statement_rule_names = [
            name
            for name, rule in self.grammar_rules.items()
            if getattr(rule, "end_case", [])
        ]
        if rules_dir:
            # 传入 rules_dir 时由调用方接管 RuleSelector，此处不创建缓存
            self.skip_types = ["newline", "space.fold"]
            categories = pratt_parser.load_token_categories(rules_dir)
            if categories:
                pratt_parser.install_token_classifier(categories)
        else:
            self.rule_selector = RuleSelector(
                self.grammar_rules,
                self.statement_rule_names,
                cache_enabled=cache_enabled,
            )
            self.skip_types = ["newline", "space.fold"]

        self.atomic_rules: List[GrammarRule] = sorted(
            (
                rule
                for rule in self.grammar_rules.values()
                if getattr(rule, "atomic", False)
            ),
            key=lambda r: len(getattr(r, "production", [])),
            reverse=True,
        )

        # inline comment 指纹匹配（解析后从源 token 流回溯）
        self._inline_comments: list[dict] = []

        self._log_state("Parser initialized", mode="w")

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
        """带级别的日志记录。

        级别规则：
          - DEBUG（默认）：仅 verbose=True 时写入
          - INFO：始终写入
          - WARN/ERROR：始终写入，ERROR 还会打印到 stderr
        """
        if level >= self.LOG_INFO or self.verbose:
            if hasattr(self, "debug_log_file"):
                indent = self._log_indent(context) if context else ""
                with open(self.debug_log_file, mode, encoding="utf-8") as f:
                    f.write(f"{indent}[{action}]\n")
        if level >= self.LOG_ERROR:
            print(f"[parser] {action}", file=sys.stderr)

    def _log_info(
        self, action: str, context: ParseContext | None = None
    ) -> None:
        """INFO 级日志：始终输出"""
        self._log_state(action, level=self.LOG_INFO, context=context)

    def _warn(self, message: str, context: ParseContext | None = None) -> None:
        """WARN 级日志：始终输出到日志文件和 stderr"""
        indent = self._log_indent(context) if context else ""
        self._log_state(
            f"WARN: {message}", level=self.LOG_WARN, context=context
        )
        print(f"[parser] {indent}⚠️ {message}", file=sys.stderr)

    @staticmethod
    def _debug_token_info(context: ParseContext) -> str:
        """返回当前 token 和 token_pointer 的调试信息字符串"""
        if context.has_more_tokens():
            tok = context.peek_token()
            return f"tok='{tok.content}' type={tok.type} idx={context.token_pointer}"
        return f"tok=EOF idx={context.token_pointer}"

    def _expected_tokens_for_rule(self, rule: GrammarRule) -> str:
        """计算规则可能接受的起始 token 类型集合，返回可读描述。"""
        from .feature_analyze import analyze_production_features
        prods = getattr(rule, "production", [])
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
            return f"{{{', '.join(sorted_starts[:10])}, ...}} ({len(sorted_starts)} total)"
        return f"{{{', '.join(sorted_starts)}}}"

    def _skip_tokens(self, context: ParseContext, skip_types: tuple) -> None:
        while context.has_more_tokens():
            cur = context.peek_token()
            if cur and cur.type in skip_types:
                context.advance_token()
            else:
                break

    @staticmethod
    def _restore_current_node(old_node: Optional[Node], context: ParseContext) -> None:
        if old_node is None:
            context.current_node = None
        else:
            context.update_current_node(old_node)

    def parse(self, tokens: List[Token]) -> Optional[Node]:
        """解析器的入口：token 流 → AST"""
        # 每次 parse 重置状态
        self._inline_comments = []
        self._failure_attempts = []
        self._parse_tokens = tokens  # 供指纹回溯用
        context = ParseContext(tokens)

        try:
            # 语义路径：Root 规则路径入栈
            context.sibling_counter["Root"] = 1
            context.path_stack.append("Root[0]")
            block_node = self.parse_block(context, start_token="")
            context.path_stack.pop()
            # 保存 comment_table 供后续消费
            self._comment_table = dict(context.comment_table)
            # 指纹定宽：从源 token 流回溯 + 最小唯一宽度
            self._resolve_fingerprints()
            if block_node is None:
                self._dump_failure_summary(context)
            return block_node if block_node else None

        except ParseError:
            # ParseError 已在抛出处打印了详细上下文
            self._dump_failure_summary(context)
            raise
        except Exception as exc:
            self._log_info(
                f"解析异常: {exc} | token={self._debug_token_info(context)}"
            )
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
        print(f"[parser]  ═══ 当前 token: {self._debug_token_info(context)} ═══", file=sys.stderr)

    @staticmethod
    def _preceding_tokens(tokens: list[Token], idx: int, n: int = 8) -> list[str]:
        """从源 token 流中回溯 idx 之前的 N 个非空白/注释 token 的内容"""
        result: list[str] = []
        while idx >= 0 and len(result) < n:
            t = tokens[idx]
            if t.type not in ("comment", "newline", "space.fold"):
                result.insert(0, t.content)
            idx -= 1
        return result

    def _resolve_fingerprints(self) -> None:
        """从源 token 流回溯取指纹 + 动态窗缩小到最小无冲突宽度

        指纹为 token 内容列表（不受渲染器空白变化影响）。
        先按 (text, line) 去重消除回溯导致的重复收集。
        """
        if not self._inline_comments:
            return

        # 去重
        seen_keys: set[tuple[str, int]] = set()
        unique: list[dict] = []
        for c in self._inline_comments:
            key = (c["text"], c["line"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(c)
        self._inline_comments = unique

        # 从源 token 流回溯取指纹
        tokens: list[Token] = getattr(self, "_parse_tokens", [])
        for c in self._inline_comments:
            c["tokens"] = self._preceding_tokens(tokens, c["token_index"])
            del c["token_index"]

        # 动态窗缩小到最小无冲突宽度（至少 2，最大不超过素材长度）
        min_tokens = min(len(c["tokens"]) for c in self._inline_comments)
        width = 2
        while width <= min_tokens:
            seen: set[tuple[str, ...]] = set()
            ok = True
            for c in self._inline_comments:
                fp = tuple(c["tokens"][-width:])
                if fp in seen:
                    ok = False
                    break
                seen.add(fp)
            if ok:
                break
            width += 1
        for c in self._inline_comments:
            c["fingerprint"] = c["tokens"][-width:]
            del c["tokens"]
