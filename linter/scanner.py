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

Doc: docs/linter_architecture.md
Doc: docs/decisions/0001-pre-parse-linter.md
"""

import os

from core.define import GrammarRule
from core.config_registry import ConfigRegistry
from lexer import Lexer
from parser import setup_grammar
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position
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
        register=None,
    ):
        """register: GrammarRulesRegister 实例。默认全局单例；多语言场景
        （如 c4 测试）应传独立实例——单例的 self.rules 累积多目录规则，
        切语言时旧语言规则会混入新语言规则表。"""
        self._rules_dir = rules_dir
        ext_list = ext_dirs or []
        ConfigRegistry.load_all(
            rules_dir,
            ext_dirs=ext_list,
            plugins_dir=os.path.join(rules_dir, "plugins"),
        )
        from core.define import GrammarRulesRegister

        if register is None:
            register = GrammarRulesRegister.get_default()
        rules = setup_grammar(
            rules_dir, register, ext_dirs=ext_list
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
            t for t in self._block_openers if t.startswith("bracket.")
        )
        self._bracket_closers = frozenset(
            t for t in self._block_closers if t.startswith("bracket.")
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
        # 后置注入：ExpressionChecker 的 pratt 原子回调复用共享 matcher 的
        # production 驱动原子匹配（参考 parser atomic_rules 流程，不手写原子逻辑）
        self._expr_checker.set_atom_matcher(self._matcher)

        self._discovery = Discovery(
            self._tree,
            self._block_openers,
            self._block_closers,
            self._all_bracket_openers,
            self._all_bracket_closers,
            matcher=self._matcher,
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

    def scan(
        self,
        source: str,
        *,
        predefined: dict[str, str] | None = None,
        undefine: set[str] | None = None,
    ) -> list[LintDiagnostic]:
        errors: list = []
        macro_defs, func_macros, _, _, _, clean_source = scan_directives(
            source, self._rules_dir, predefined=predefined, undefine=undefine
        )
        if macro_defs:
            lex_source, _ = expand_tokens(
                clean_source, macro_defs, prefix=self._macro_prefix,
                func_macros=func_macros,
            )
        elif clean_source != source:
            lex_source = clean_source
        else:
            lex_source = source

        try:
            tokens = self.lexer.tokenize(lex_source)
        except Exception as exc:
            # 通用防御：lexer 无法处理输入（不支持的字符/行尾风格/BOM 等）时
            # 转诊断而非崩溃冒泡——否则调用方（CLI/编辑器集成）直接异常。
            # 不硬编码具体格式（CRLF/BOM 等由 lexer 侧支持），此处只对
            # "lexer 异常"这一通用情况做响应；lexer 修复后输入自然正常解析。
            return [
                LintDiagnostic(
                    range=(Position(0, 0), Position(0, 0)),
                    message=f"lexer error: {exc}",
                    severity=1,
                    code="lexer-error",
                )
            ]
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
        # discovery 产出多层级树（children 嵌套）；深度优先遍历把每个节点
        # 注册为独立 StatementChecker——父节点按 production 匹配（@Stmt 由
        # matcher 用 end_case 扁平跳过），子节点独立检查自身区间，扁平验证。
        if self.enable_phase2:
            def register(node) -> None:
                registry.add(
                    StatementChecker(
                        node.rule,
                        node.start,
                        node.end,
                        self._matcher,
                    )
                )
                for child in node.children:
                    register(child)

            for node in self._discovery.discover(tokens):
                register(node)

        # 未识别语句诊断（发现阶段记录）与各 Checker 诊断合并输出。
        errors = self._discovery.unrecognized_diagnostics()
        errors += registry.validate_all(tokens)
        return errors
