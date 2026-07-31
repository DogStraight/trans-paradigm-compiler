"""
scanner.py — 两阶段 Linter 编排器。

发现阶段（discovery.py）：
    token 流 → 自动注册的扁平节点列表（轻量 AST）

检查阶段（checkers/）：
    每个节点实例化对应 Checker，扁平 validate，合并错误
        boundary.py    — 块边界配对（原 P1）
        macro_token.py — 非法 token（原 P0）
        statement.py   — 语句结构（从 production 编译）
        expression.py  — 表达式（借力 parser pratt）

每层可独立开关。LinterScanner(...) 构造时通过 enable_phase0/1/2 控制。
"""

import os

from core.define import GrammarRule
from core.config_registry import ConfigRegistry
from lexer import Lexer
from parser import setup_grammar
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic
from ._constants import BRACKET_TOKEN_PREFIX
from .grammar_slicer import build_slice_tree
from .discovery import Discovery
from .checker import CheckerRegistry
from .checkers.boundary import BoundaryChecker
from .checkers.macro_token import MacroTokenChecker
from .checkers.statement import StatementChecker
from .checkers.expression import ExpressionChecker


class LinterScanner:
    def __init__(
        self,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        enable_phase0: bool = True,
        enable_phase1: bool = True,
        enable_phase2: bool = True,
    ):
        self._rules_dir = rules_dir
        ext_list = ext_dirs or []
        ConfigRegistry.load_all(
            rules_dir,
            ext_dirs=ext_list,
            plugins_dir=os.path.join(rules_dir, "plugins"),
        )
        from core.define import GrammarRulesRegister

        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ext_list
        )
        self._tree = build_slice_tree(rules)
        self.lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_list)

        self._macro_prefix, _ = _load_config()

        # ── 动态收集 block 起止符 ─────────────────
        _openers, _closers, self._block_pairs, _ = self._build_block_delimiters(rules)

        # 括号配对单一来源：lexer.bracket_map（规则侧 bracket bound 已移除，
        # 括号由 [bracket].pairs 统一定义）。括号同时加入 block 起止符集，
        # 使 BoundaryChecker 的栈式配对与 matcher 的括号上下文检查正常生效。
        _raw_pairs = ConfigRegistry._loaded.get("lexer.bracket_map", {}).get("pairs", [])
        _bracket_pairs: dict[str, set[str]] = {}
        for _l, _r, _name in _raw_pairs:
            _lt = f"bracket.l_{_name}"
            _rt = f"bracket.r_{_name}"
            _openers.add(_lt)
            _closers.add(_rt)
            _bracket_pairs.setdefault(_rt, set()).add(_lt)

        self._block_openers = frozenset(_openers)
        self._block_closers = frozenset(_closers)
        for _rt, _ls in _bracket_pairs.items():
            self._block_pairs.setdefault(_rt, set()).update(_ls)
        self._bracket_openers = frozenset(
            t for t in self._block_openers if t.startswith(BRACKET_TOKEN_PREFIX)
        )
        self._bracket_closers = frozenset(
            t for t in self._block_closers if t.startswith(BRACKET_TOKEN_PREFIX)
        )
        self._all_bracket_openers = self._bracket_openers
        self._all_bracket_closers = self._bracket_closers

        # 表达式检查器（借力 pratt）+ 共享规则匹配器
        from parser.pratt_parser import process_operator_data

        raw_ops = ConfigRegistry._loaded.get("parser.operator_defs", [])
        self._expr_checker = ExpressionChecker(process_operator_data(raw_ops))
        from .checkers.matcher import RuleMatcher

        self._matcher = RuleMatcher(
            self._tree,
            self._expr_checker,
            self._block_openers,
            self._block_closers,
        )

        _opener_ctx = {
            k: v for k, v in ConfigRegistry._loaded.get("linter.opener_context", [])
        }
        self._discovery = Discovery(
            self._tree,
            self._block_openers,
            self._block_closers,
            self._all_bracket_openers,
            self._all_bracket_closers,
            opener_ctx=_opener_ctx,
            module_item_rule=ConfigRegistry._loaded.get(
                "linter.module_item_rule", "ModuleItem"
            ),
            stmt_rule=ConfigRegistry._loaded.get("linter.stmt_rule", "Stmt"),
        )

        self.enable_phase0 = enable_phase0
        self.enable_phase1 = enable_phase1
        self.enable_phase2 = enable_phase2

    # ── 动态 block delimiter 收集 ─────────────────

    @staticmethod
    def _build_block_delimiters(
        rules: dict,
    ) -> tuple[set[str], set[str], dict[str, set[str]], dict[str, str]]:
        """从语法规则的 bound 字段收集起止符集合及配对映射。

        Returns: (openers, closers, closer_to_openers, opener_to_rule)
            closer_to_openers — 每个 closer token 对应的有效 opener token 集合。
            opener_to_rule    — 每个 opener token 对应的规则名称（用于骨架上上文）。
        """
        openers: set[str] = set()
        closers: set[str] = set()
        closer_to_openers: dict[str, set[str]] = {}
        opener_to_rule: dict[str, str] = {}
        for name, rule in rules.items():
            if not isinstance(rule, GrammarRule):
                continue
            bs = getattr(rule, "block_start", "") or ""
            be = getattr(rule, "block_end", "") or ""
            if not bs and not be:
                continue
            if bs:
                openers.add(bs)
                # 第一个声明该 block 的规则胜出
                if bs not in opener_to_rule:
                    opener_to_rule[bs] = name
            if be:
                closers.add(be)
            if bs and be:
                closer_to_openers.setdefault(be, set()).add(bs)
        return openers, closers, closer_to_openers, opener_to_rule

    def scan(self, source: str) -> list[LintDiagnostic]:
        errors: list = []
        macro_defs, _, clean_source = scan_directives(source, self._rules_dir)
        if macro_defs:
            lex_source, _ = expand_tokens(
                clean_source, macro_defs, prefix=self._macro_prefix
            )
        elif clean_source != source:
            lex_source = clean_source
        else:
            lex_source = source

        tokens = self.lexer.tokenize(lex_source)
        if not tokens:
            return errors

        registry = CheckerRegistry()

        # ── P1: 块边界配对 ──────────────────────
        if self.enable_phase1:
            registry.add(
                BoundaryChecker(
                    0,
                    len(tokens),
                    self._block_openers,
                    self._block_closers,
                    self._block_pairs,
                )
            )

        # ── P0: 非法 token 检查 ─────────────────
        if self.enable_phase0:
            registry.add(MacroTokenChecker(0, len(tokens)))

        # ── P2: 语句发现 + 扁平检查 ─────────────
        if self.enable_phase2:
            for node in self._discovery.discover(tokens):
                registry.add(
                    StatementChecker(
                        node.rule,
                        node.start,
                        node.end,
                        self._matcher,
                    )
                )

        return registry.validate_all(tokens)
