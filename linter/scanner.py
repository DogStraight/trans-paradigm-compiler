"""
scanner.py — Linter 扫描核心

职责：
- 轻量级逐句扫描，出错跳过并继续
- 宏指令语法校验（复用 Parser 的解析能力）
- 输出 LSP 兼容的诊断信息
"""

from typing import Optional, Dict, List, Set
import re

from core.define import GrammarRule
from core.config_registry import ConfigRegistry
from lexer import Lexer
from parser import Parser, setup_grammar
from parser.rule_selector import RuleSelector
from parser.parser_core import ParseContext
from parser.block_parser import _get_block_end
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position


class LinterScanner:
    """轻量级语法扫描器。"""

    def __init__(self, rules_dir: str, ext_dir: str = ""):
        self._rules_dir = rules_dir
        ConfigRegistry.load_all(rules_dir, ext_dir=ext_dir)
        from core.define import GrammarRulesRegister

        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dir
        )
        stmt_names = [
            n for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rule_selector = RuleSelector(rules, stmt_names, cache_enabled=False)
        self.lexer = Lexer(rules_dir=rules_dir)
        self.parser = Parser(rules=rules, rule_selector=rule_selector, cache_enabled=False)

        # 推导边界 Token + 语句起始 Token
        self._boundary_tokens: Set[str] = self._derive_boundary_tokens(rules)
        self._statement_starts: Set[str] = self._derive_statement_starts(rules)
        self._trivia_types = tuple(self.parser.skip_types) + ("comment",)

        # 宏前缀
        self._macro_prefix, _ = _load_config(rules_dir)

    # ── 静态辅助 ──────────────────────────────────────────

    @staticmethod
    def _derive_boundary_tokens(rules: Dict[str, GrammarRule]) -> Set[str]:
        boundary: Set[str] = set()
        for rule in rules.values():
            for item in getattr(rule, "end_case", []):
                if isinstance(item, str) and not item.startswith("!"):
                    boundary.add(item)
            if getattr(rule, "is_block", False):
                end = _get_block_end(rule)
                if end:
                    boundary.add(end)
        return boundary

    @staticmethod
    def _derive_statement_starts(rules: Dict[str, GrammarRule]) -> Set[str]:
        """从有 end_case 的规则中提取首 token 集合，用于智能跳过。"""
        starts: Set[str] = set()
        for rule in rules.values():
            ec = getattr(rule, "end_case", None)
            if not ec:
                continue
            prods = getattr(rule, "production", [])
            if not prods:
                continue
            first = prods[0]
            # keyword.module → keyword.module
            # keyword.case|keyword.casex → 展开分支
            for part in first.split("|"):
                part = part.strip()
                if part.startswith("@"):
                    # @RuleRef — 找被引用规则的首 token
                    ref_rule = rules.get(part[1:])
                    if ref_rule:
                        ref_prods = getattr(ref_rule, "production", [])
                        if ref_prods:
                            for ref_part in ref_prods[0].split("|"):
                                ref_part = ref_part.strip()
                                if not ref_part.startswith("@"):
                                    starts.add(ref_part)
                else:
                    starts.add(part)
        return starts

    # ── 公开入口 ──────────────────────────────────────────

    def scan(self, source: str) -> List[LintDiagnostic]:
        """扫描源代码，返回所有诊断信息。"""

        errors: List[LintDiagnostic] = []
        prefix = self._macro_prefix

        # Stage 1: 提取宏定义，校验宏指令语法
        macro_defs, directive_lines, clean_source = scan_directives(source, self._rules_dir)
        self._validate_directives(directive_lines, macro_defs, prefix, errors)

        # Stage 1.5: 展开前校验宏调用（宏名是否已定义）
        self._validate_macro_calls(clean_source, macro_defs, prefix, errors)

        # Stage 2: 展开宏调用，扫描纯代码
        if macro_defs:
            expanded, _ = expand_tokens(clean_source, macro_defs, prefix=prefix)
            lex_source = expanded
        elif directive_lines:
            lex_source = clean_source
        else:
            lex_source = source

        tokens = self.lexer.tokenize(lex_source)
        context = ParseContext(tokens)
        self._scan_block(context, errors)
        return errors

    # ── 宏调用校验 ──────────────────────────────────────

    def _validate_macro_calls(
        self,
        source: str,
        macro_defs: Dict[str, str],
        prefix: str,
        errors: List[LintDiagnostic],
    ) -> None:
        """展开前校验宏调用：检查宏名是否已定义。"""
        import re
        pattern = re.compile(re.escape(prefix) + r"(\w+)")
        # clean_source 已去掉指令行，所有宏调用都是展开引用
        for i, line in enumerate(source.split("\n"), 1):
            for m in pattern.finditer(line):
                name = m.group(1)
                if name not in macro_defs:
                    pos = Position(line=max(0, i - 1), character=m.start())
                    errors.append(LintDiagnostic(
                        range=(pos, pos),
                        message=f"undefined macro: '{name}'",
                        severity=1,
                        code="macro-undefined",
                    ))

    # ── 宏指令校验 ──────────────────────────────────────

    def _validate_directives(
        self,
        directive_lines: List[str],
        macro_defs: Dict[str, str],
        prefix: str,
        errors: List[LintDiagnostic],
    ) -> None:
        for line in directive_lines:
            stripped = line.strip()
            if not stripped.startswith(prefix) or not stripped[1:].isalpha():
                continue

            if prefix in stripped[1:] and macro_defs:
                expanded = re.sub(
                    re.escape(prefix) + r"(\w+)",
                    lambda m: macro_defs.get(m.group(1), m.group(0)),
                    stripped,
                )
            else:
                expanded = stripped

            tokens = self.lexer.tokenize(expanded + "\n")
            if not tokens:
                continue

            ctx = ParseContext(tokens)
            while ctx.has_more_tokens():
                t = ctx.peek_token()
                if t and t.type in self._trivia_types:
                    ctx.advance_token()
                else:
                    break

            t = ctx.peek_token()
            if t and t.type.startswith("macro.") and t.type != "macro.call":
                if self.parser.parse_sentence(ctx) is None:
                    errors.append(LintDiagnostic(
                        range=(Position(0, 0), Position(0, 0)),
                        message=f"macro syntax error: {stripped}",
                        severity=1,
                        code="macro-syntax-error",
                    ))

    # ── 核心扫描 ──────────────────────────────────────────

    def _scan_block(
        self,
        context: ParseContext,
        errors: List[LintDiagnostic],
        end_token: str = "",
    ) -> None:
        """扫描一个块体：逐句匹配，失败则记录并跳过。"""
        while context.has_more_tokens():
            self._skip_trivia(context)
            if not context.has_more_tokens():
                break

            current = context.peek_token()
            assert current is not None

            if end_token and current.type == end_token:
                break

            stmt = self.parser.parse_sentence(context)
            if stmt is not None:
                continue

            # 宏调用 token：跳过即可（未定义宏已在 _validate_macro_calls 中报过）
            if current.type.startswith("macro."):
                context.advance_token()
                continue

            # 匹配失败：记录错误并跳过
            start_pos = Position(
                line=max(0, current.line - 1),
                character=max(0, current.column - 1)
            )
            self._skip_to_boundary(context, end_token)
            end_pos = self._current_position(context)
            errors.append(
                LintDiagnostic(
                    range=(start_pos, end_pos),
                    message=f"syntax error: cannot match statement (starting token '{current.content}')",
                    severity=1,
                    code="parse-error",
                )
            )

    # ── 辅助方法 ──────────────────────────────────────────

    def _skip_trivia(self, context: ParseContext) -> None:
        while context.has_more_tokens():
            t = context.peek_token()
            if t and t.type in self._trivia_types:
                context.advance_token()
            else:
                break

    def _skip_to_boundary(self, context: ParseContext, block_end: str = "") -> None:
        """跳过 token 直到下一个安全边界：分号或块结束符。"""
        # 当前 token 已匹配失败，先消耗再跳
        context.advance_token()
        while context.has_more_tokens():
            t = context.peek_token()
            assert t is not None
            if block_end and t.type == block_end:
                return
            if t.type in self._boundary_tokens:
                if t.type == "symbol.base.semicolon":
                    context.advance_token()
                    return
                if t.type.startswith("keyword.end"):
                    context.advance_token()
                    return
            context.advance_token()

    @staticmethod
    def _current_position(context: ParseContext) -> Position:
        t = context.peek_token()
        if t:
            return Position(line=max(0, t.line - 1), character=max(0, t.column - 1))
        if context.token_pointer > 0:
            prev = context.tokens[context.token_pointer - 1]
            return Position(
                line=max(0, prev.line - 1),
                character=max(0, prev.column - 1)
            )
        return Position(line=0, character=0)