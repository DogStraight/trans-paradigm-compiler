# parser/main_parser.py
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

    def __init__(self, rules_dir: str | None = None) -> None:
        self.grammar_rules: Dict[str, GrammarRule] = {}
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
            if getattr(rule, "end_case") is not None
        ]
        self.rule_selector = RuleSelector(self.grammar_rules, self.statement_rule_names)
        self.skip_types = ["newline", "space.fold"]

        if rules_dir:
            categories = pratt_parser.load_token_categories(rules_dir)
            if categories:
                pratt_parser.install_token_classifier(categories)

        self.atomic_rules: List[GrammarRule] = sorted(
            (
                rule
                for rule in self.grammar_rules.values()
                if getattr(rule, "atomic", False)
            ),
            key=lambda r: len(getattr(r, "production", [])),
            reverse=True,
        )
        self._log_state("Parser initialized", mode="w")

    def _log_state(self, action: str, mode: str = "a") -> None:
        if hasattr(self, "debug_log_file"):
            with open(self.debug_log_file, mode, encoding="utf-8") as f:
                f.write(f"[{action}]\n")

    def _warn(self, message: str) -> None:
        self._log_state(f"警告: {message}")
        print(f"⚠️ [解析器] {message}", file=sys.stderr)

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
        context = ParseContext(tokens)
        block_node = self.parse_block(context, start_token="")
        return block_node if block_node else None
