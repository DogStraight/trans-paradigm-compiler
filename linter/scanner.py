"""
scanner.py — Linter 扫描核心

职责：
- 轻量级逐句扫描，出错跳过并继续
- 宏指令语法校验（复用 Parser 的解析能力）
- 输出 LSP 兼容的诊断信息
"""



from core.config_registry import ConfigRegistry
from lexer import Lexer
from parser import Parser, setup_grammar
from parser.rule_selector import RuleSelector
from parser.parser_core import ParseContext
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position
from .grammar_slicer import build_slicing_map, DeclSlice, StmtSlice, SkipSlice


class LinterScanner:
    """轻量级语法扫描器。"""

    def __init__(self, rules_dir: str, ext_dirs: list[str] | None = None):
        self._rules_dir = rules_dir
        ext_list = ext_dirs or []
        ConfigRegistry.load_all(rules_dir, ext_dirs=ext_list)
        from core.define import GrammarRulesRegister

        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ext_list
        )
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rule_selector = RuleSelector(rules, stmt_names)
        self.lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_list)
        self.parser = Parser(
            rules=rules, rule_selector=rule_selector
        )

        # 从语法规则推导切片策略 + 终止符
        self._slice_map, self._terminators = build_slicing_map(rules, stmt_names)
        self._trivia_types = tuple(self.parser.skip_types) + ("comment",)

        # 宏前缀
        self._macro_prefix, _ = _load_config()

    # ── 静态辅助 ──────────────────────────────────────────

    def _skip_to_terminator(self, context: ParseContext) -> None:
        """跳过到下一个终止符（由语法规则 end_case 推导）。"""
        while context.has_more_tokens():
            t = context.peek_token()
            assert t is not None
            if t.type in self._terminators:
                context.advance_token()
                return
            context.advance_token()

    # ── 公开入口 ──────────────────────────────────────────

    def scan(self, source: str) -> List[LintDiagnostic]:
        """扫描源代码，返回所有诊断信息。"""
        errors: List[LintDiagnostic] = []

        # 提取宏定义 + 展开
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
        context = ParseContext(tokens)
        self._scan_block(context, errors)
        return errors

    # ── 核心扫描 ──────────────────────────────────────────

    def _scan_block(
        self,
        context: ParseContext,
        errors: list[LintDiagnostic],
        end_token: str = "",
    ) -> None:
        """分层切片扫描。

        层1：声明级块（module/function/task/case → end*）— 整体跳过
        层2：逐句解析（always/if/for/assign 等）
        层3：解析失败 → 跳到分号，报告一次错误
        """
        while context.has_more_tokens():
            self._skip_trivia(context)
            if not context.has_more_tokens():
                break

            current = context.peek_token()
            assert current is not None

            if end_token and current.type == end_token:
                break

            # 从切片策略表查询当前 token 的处理方式
            strategy = self._slice_map.get(current.type)

            if isinstance(strategy, DeclSlice):
                # 声明/块头部：跳到终止符
                self._skip_to_terminator(context)
                continue

            if isinstance(strategy, StmtSlice):
                # 语句：由 parse_sentence 处理
                if self.parser.parse_sentence(context) is not None:
                    continue
                # parse_sentence 失败 → 走 error 路径
                pass

            if isinstance(strategy, SkipSlice):
                # 静默跳过
                context.advance_token()
                continue

            # 宏调用：跳过
            if current.type.startswith("macro."):
                context.advance_token()
                continue

            # 未知 token：先试 parse_sentence，失败则跳到终止符
            if self.parser.parse_sentence(context) is not None:
                continue

            start_pos = Position(
                line=max(0, current.line - 1), character=max(0, current.column - 1)
            )
            self._skip_to_terminator(context)
            errors.append(
                LintDiagnostic(
                    range=(start_pos, start_pos),
                    message=f"syntax error: unexpected '{current.content}'",
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
