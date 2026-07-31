"""checkers/statement.py — 语句检查器。

每个 StatementChecker 只检查一种语法结构（rule），在发现阶段注册的
token 区间 [start, end) 内按 production 精确匹配。匹配核心复用共享的
RuleMatcher（matcher.py），错误信息精准（token 位置知道期望值）。

扁平化策略：
    - 遇 @Expression / pratt 链 → 交 ExpressionChecker（含 atom_parser）
    - 遇嵌套 @Stmt / @BeginEnd → 用 end_case 跳过（嵌套语句由发现阶段
      注册的独立检查器负责）
    - 仅内联匹配"普通子规则"（非表达式、非语句、非块的 call）
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic
from ..checker import Checker


class StatementChecker(Checker):
    """单个语句结构的扁平检查器。"""

    def __init__(
        self,
        rule: str,
        start: int,
        end: int,
        matcher,
    ) -> None:
        self.rule = rule
        self.start = start
        self.end = end
        self._matcher = matcher
        self._prods = matcher._tree.get(rule, {}).get("prods", [])

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        errors: list[LintDiagnostic] = []
        self._matcher.match_rule(
            tokens, self.start, self._prods, errors, min(self.end, len(tokens))
        )
        return errors
