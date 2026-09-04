"""checkers/statement.py — 语句检查器。

每个 StatementChecker 只检查一种语法结构（rule），在发现阶段注册的
token 区间 [start, end) 内按 production 精确匹配。匹配核心复用共享的
RuleMatcher（matcher.py），错误信息精准（token 位置知道期望值）。

扁平化策略：
    - 遇 @Expression / pratt 链 → 交 ExpressionChecker（含 atom_parser）
    - 遇嵌套 @Stmt / @BeginEnd → 用 end_case 跳过（嵌套语句由发现阶段
      注册的独立检查器负责）
    - 仅内联匹配"普通子规则"（非表达式、非语句、非块的 call）
Doc: linter/linter_architecture.md（P2 语句检查器）
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic, token_span
from ..checker import Checker


class StatementChecker(Checker):
    """单个语句结构的扁平检查器。"""

    def __init__(
        self,
        rule: "str | list[str]",
        start: int,
        end: int,
        matcher,
    ) -> None:
        # 同一起始 token 可对应多个候选规则（如 TaskDeclANSI/Old、FuncDeclANSI/Old）
        self.rules = rule if isinstance(rule, (list, tuple)) else [rule]
        self.start = start
        self.end = end
        self._matcher = matcher

    def _try_rule(self, tokens: list[Token], rule: str) -> list[LintDiagnostic]:
        errors: list[LintDiagnostic] = []
        prods = self._matcher._tree.get(rule, {}).get("prods", [])
        start = self.start
        # 块规则：production 不含 block.start（如 ModuleDecl 从 @Identifier 开始），
        # 需先校验并消费 block.start token，再按 production 匹配块内容。
        bs = (self._matcher._tree.get(rule, {}) or {}).get("block_start") or ""
        if bs:
            if start < len(tokens) and tokens[start].type == bs:
                start += 1
            else:
                t = tokens[start]
                errors.append(
                    LintDiagnostic(
                        range=token_span(t),
                        message=f"expected block start '{bs}', got '{t.content}'",
                        severity=1,
                        code="phase-statement",
                    )
                )
                start += 1
        self._matcher.match_rule(
            tokens, start, prods, errors, min(self.end, len(tokens))
        )
        return errors

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        """对每个候选规则尝试匹配：无错误的候选立即胜出，
        全部有错时取错误最少的候选（还原旧 P2 的多候选取优行为）。"""
        best: list[LintDiagnostic] | None = None
        for rule in self.rules:
            errs = self._try_rule(tokens, rule)
            if not errs:
                return errs
            if best is None or len(errs) < len(best):
                best = errs
        return best or []
