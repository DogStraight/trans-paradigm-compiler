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
from core.define import Node, Token, GrammarRule, GrammarRulesRegister, FileManager
from .parser_context import ParseContext
from .rule_selector import RuleSelector
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
    ) -> None:
        self.grammar_rules: Dict[str, GrammarRule] = {}
        self._cache_enabled = cache_enabled
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

    def _log_state(self, action: str, mode: str = "a") -> None:
        if hasattr(self, "debug_log_file"):
            with open(self.debug_log_file, mode, encoding="utf-8") as f:
                f.write(f"[{action}]\n")

    def _warn(self, message: str) -> None:
        self._log_state(f"WARN: {message}")
        print(f"[parser] {message}", file=sys.stderr)

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
        # 每次 parse 重置 inline comment 收集状态
        self._inline_comments = []
        self._parse_tokens = tokens  # 供指纹回溯用
        context = ParseContext(tokens)
        # 语义路径：Root 规则路径入栈
        context.sibling_counter["Root"] = 1
        context.path_stack.append("Root[0]")
        block_node = self.parse_block(context, start_token="")
        context.path_stack.pop()
        # 保存 comment_table 供后续消费
        self._comment_table = dict(context.comment_table)
        # 指纹定宽：从源 token 流回溯 + 最小唯一宽度
        self._resolve_fingerprints()
        return block_node if block_node else None

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
