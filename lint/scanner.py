"""
scanner.py — Linter 扫描核心

复用 Parser 的 parse_sentence 和 parse_block，但控制流不同：
主解析器遇到失败就停，linter 记错后跳过继续。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.define import GrammarRule, GrammarRulesRegister
from parser.parser_core import Parser, ParseContext
from parser.block_parser import _get_block_end
from parser.rule_selector import RuleSelector
from parser import setup_grammar
from lexer import Lexer
from core.config_registry import ConfigRegistry
from . import LintDiagnostic, Position


# 跳过边界 token 类型集合
_BOUNDARY_TOKENS = {
    "symbol.base.semicolon",
    "keyword.end",
    "keyword.endmodule",
    "keyword.endcase",
    "keyword.endfunction",
    "keyword.endtask",
    "keyword.endgenerate",
    "keyword.endclass",
    "keyword.endspecify",
    "keyword.endtable",
    "keyword.endprimitive",
}


class LinterScanner:
    """轻量语法扫描器：共享 Parser 的 TOML 语法配置，只输出诊断不建 AST。"""

    def __init__(
        self,
        rules_dir: str = "pyv_compiler/grammar/rules_verilog",
        ext_dir: str = "pyv_compiler/grammar/rules_verilog_ext",
    ):
        # 加载配置注册表（Parser/Lexer 需要）
        ConfigRegistry.load_all(rules_dir, ext_dir=ext_dir)
        # 加载语法规则（含 EXT 注入），使用新注册器避免缓存污染
        self.rules = setup_grammar(rules_dir, GrammarRulesRegister(), ext_dir)
        stmt_names = [
            n for n, r in self.rules.items()
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
        # 收集块规则结束符映射
        self._block_ends: dict[str, str] = {}
        for name, rule in self.parser.grammar_rules.items():
            if getattr(rule, "is_block", False):
                end = _get_block_end(rule)
                if end:
                    self._block_ends[name] = end

    # ── 公开入口 ──────────────────────────────────────────

    def scan(self, source: str) -> list[LintDiagnostic]:
        """扫描源代码，返回所有诊断信息。"""
        tokens = self.lexer.tokenize(source)
        context = ParseContext(tokens)
        errors: list[LintDiagnostic] = []
        self._scan_block(context, errors)
        return errors

    # ── 内部扫描 ──────────────────────────────────────────

    def _scan_block(self, context: ParseContext, errors: list[LintDiagnostic],
                    end_token: str = "") -> None:
        """扫描一个块体：逐句匹配，失败则记录并跳过。"""
        while context.has_more_tokens():
            # 跳过空白 + 注释
            self._skip_trivia(context)
            if not context.has_more_tokens():
                break

            current = context.peek_token()
            assert current is not None

            # 块结束符
            if end_token and current.type == end_token:
                break

            # 跳过宏指令行（`define / `include / `ifdef 等）
            if self._skip_macro_line(context):
                continue

            # 尝试匹配一条语句
            stmt = self.parser.parse_sentence(context)
            if stmt is not None:
                continue

            # ── 匹配失败：记录错误，跳过 ──
            start_pos = Position(line=max(0, current.line - 1), character=max(0, current.column - 1))
            self._skip_to_boundary(context, end_token)

            # 确定结束位置
            end_pos = self._current_position(context)
            errors.append(LintDiagnostic(
                range=(start_pos, end_pos),
                message=f"语法错误：无法匹配语句（起始 token '{current.content}'）",
            ))

    # ── 跳过辅助 ──────────────────────────────────────────

    def _skip_trivia(self, context: ParseContext) -> None:
        """跳过空白（newline / space.fold / comment）。"""
        while context.has_more_tokens():
            t = context.peek_token()
            if t and t.type in ("newline", "space.fold", "comment"):
                context.advance_token()
            else:
                break

    def _skip_macro_line(self, context: ParseContext) -> bool:
        """如果当前 token 是 macro.*，跳过整行（到 newline）。返回 True 跳过了。"""
        t = context.peek_token()
        if t and t.type.startswith("macro."):
            # 跳过 macro 指令 token 和行内剩余所有 token
            while context.has_more_tokens():
                cur = context.peek_token()
                if cur is None or cur.type == "newline":
                    return True
                context.advance_token()
            return True
        return False

    def _skip_to_boundary(self, context: ParseContext, block_end: str = "") -> None:
        """跳过 token 直到下一个安全边界（; 或块结束符或 start_token）。"""
        while context.has_more_tokens():
            t = context.peek_token()
            assert t is not None

            # 块结束符边界
            if block_end and t.type == block_end:
                return

            # 通用边界
            if t.type in _BOUNDARY_TOKENS:
                context.advance_token()  # 消费掉边界 token
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
            return Position(line=max(0, prev.line - 1), character=max(0, prev.column - 1))
        return Position(line=0, character=0)
