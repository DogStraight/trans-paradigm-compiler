"""
scanner.py — Linter 扫描核心

流程：提取宏定义 → 文本层展开宏调用 → 词法分析 → parse_sentence 逐句扫描。
语法来源单一且静态：Parser 的 TOML 语法配置，linter 不维护额外状态。
"""

from core.define import GrammarRulesRegister
from parser.parser_core import Parser, ParseContext
from parser.block_parser import _get_block_end
from parser.rule_selector import RuleSelector
from parser import setup_grammar
from lexer import Lexer
from core.config_registry import ConfigRegistry
from . import LintDiagnostic, Position


class LinterScanner:
    """轻量语法扫描器：共享 Parser 的 TOML 语法配置，只输出诊断不建 AST。"""

    def __init__(self, rules_dir: str, ext_dir: str):
        self.rules_dir = rules_dir
        self.ext_dir = ext_dir
        ConfigRegistry.load_all(rules_dir, ext_dir=ext_dir)
        self.rules = setup_grammar(rules_dir, GrammarRulesRegister(), ext_dir)
        stmt_names = [
            n
            for n, r in self.rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        self.rule_selector = RuleSelector(self.rules, stmt_names, cache_enabled=False)
        self.lexer = Lexer(rules_dir=rules_dir)
        self.parser = Parser(
            rules_dir=rules_dir,
            cache_enabled=False,
            rules=self.rules,
            rule_selector=self.rule_selector,
        )

        # ── 从语法规则推导边界 token（替代硬编码）──
        boundary: set[str] = set()
        for rule in self.rules.values():
            for item in getattr(rule, "end_case", []):
                if isinstance(item, str) and not item.startswith("!"):
                    boundary.add(item)
            if getattr(rule, "is_block", False):
                end = _get_block_end(rule)
                if end:
                    boundary.add(end)
        self._boundary_tokens = boundary

        # 跳过类型：复用 Parser 的 skip_types + comment
        self._trivia_types = tuple(self.parser.skip_types) + ("comment",)

    # ── 公开入口 ──────────────────────────────────────────

    def scan(self, source: str) -> list[LintDiagnostic]:
        """扫描源代码，返回所有诊断信息。

        两阶段：
        1. 校验宏指令语法，含内嵌宏调用展开
        2. 展开宏调用后扫描纯代码
        """
        from preprocessor._expand import scan_directives, expand_tokens, _load_config

        errors: list[LintDiagnostic] = []

        # 获取宏前缀（如 `）
        prefix, _ = _load_config(self.rules_dir)

        # ── Stage 1: 提取宏定义，校验宏指令语法 ──
        macro_defs, directive_lines, clean_source = scan_directives(
            source, self.rules_dir
        )
        self._validate_directives(directive_lines, macro_defs, prefix, errors)

        # ── Stage 2: 展开宏调用，扫描纯代码 ──
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

    # ── 宏指令语法校验 ──────────────────────────────────

    def _validate_directives(
        self,
        directive_lines: list[str],
        macro_defs: dict[str, str],
        prefix: str,
        errors: list[LintDiagnostic],
    ) -> None:
        """用 TOML 语法规则校验宏指令行。"""
        import re

        # 全新规则 + Parser（_prod_cache 已移除，GrammarRule 无共享状态）
        val_rules = setup_grammar(self.rules_dir, GrammarRulesRegister(), self.ext_dir)
        val_stmt = [
            n for n, r in val_rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        val_sel = RuleSelector(val_rules, val_stmt, cache_enabled=False)
        val_parser = Parser(
            rules_dir=self.rules_dir,
            cache_enabled=False,
            rules=val_rules,
            rule_selector=val_sel,
        )

        for line in directive_lines:
            stripped = line.strip()
            if not stripped.startswith(prefix) or not stripped[1:].isalpha():
                continue

            # 展开内嵌宏调用（如宏体内引用其他宏）
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
            # 跳过前导新行/空格
            while ctx.has_more_tokens():
                t = ctx.peek_token()
                if t and t.type in self._trivia_types:
                    ctx.advance_token()
                else:
                    break

            t = ctx.peek_token()
            if t and t.type.startswith("macro.") and t.type != "macro.call":
                if val_parser.parse_sentence(ctx) is None:
                    errors.append(LintDiagnostic(
                        range=(Position(0, 0), Position(0, 0)),
                        message=f"macro syntax error: {stripped}",
                        severity=1,
                        code="macro-syntax-error",
                    ))

    # ── 内部扫描 ──────────────────────────────────────────

    def _scan_block(
        self, context: ParseContext, errors: list[LintDiagnostic], end_token: str = ""
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

            # ── 匹配失败：记录错误，跳过 ──
            start_pos = Position(
                line=max(0, current.line - 1), character=max(0, current.column - 1)
            )
            self._skip_to_boundary(context, end_token)
            end_pos = self._current_position(context)
            errors.append(
                LintDiagnostic(
                    range=(start_pos, end_pos),
                    message=f"syntax error: cannot match statement (starting token '{current.content}')",
                )
            )

    # ── 跳过辅助 ──────────────────────────────────────────

    def _skip_trivia(self, context: ParseContext) -> None:
        """跳过空白/注释 token（类型由语法配置驱动）。"""
        while context.has_more_tokens():
            t = context.peek_token()
            if t and t.type in self._trivia_types:
                context.advance_token()
            else:
                break

    def _skip_to_boundary(self, context: ParseContext, block_end: str = "") -> None:
        """跳过 token 直到下一个安全边界（; 或块结束符）。"""
        while context.has_more_tokens():
            t = context.peek_token()
            assert t is not None

            if block_end and t.type == block_end:
                return

            if t.type in self._boundary_tokens:
                context.advance_token()
                return

            context.advance_token()

    @staticmethod
    def _current_position(context: ParseContext) -> Position:
        """返回当前 token 的 LSP 兼容位置（0-based，clamp >=0）。"""
        t = context.peek_token()
        if t:
            return Position(line=max(0, t.line - 1), character=max(0, t.column - 1))
        # EOF：用上一个 token 的行列
        if context.token_pointer > 0:
            prev = context.tokens[context.token_pointer - 1]
            return Position(
                line=max(0, prev.line - 1), character=max(0, prev.column - 1)
            )
        return Position(line=0, character=0)
