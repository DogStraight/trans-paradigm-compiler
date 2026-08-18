"""checkers/expression.py — 表达式检查器（复用 parser 的 pratt 部分）。

设计：表达式处理完全复用解析器能力，不在代码中固化任何组合逻辑。
    - 运算符链 / 中缀 / 优先级：parse_with_count + parser.operator_defs（配置驱动）。
    - 原子（BitWidthLiteral / SelectExpr / ConcatExpr / ReplicateExpr /
      CallExpr / SysFuncCall / ParenthesizedExpr / 括号）：交给共享 RuleMatcher
      按 is_atom 规则的 production 内联匹配，参考 parser 的 atomic_rules 流程
      （收集 is_atom 规则、按 production 长度降序逐个尝试），不手写。

左递归约束：表达式文法暗含（间接）左递归环（@Expression ⇄ @PrimaryExpr ⇄
@SelectSuffix/@ParenthesizedExpr/...），LL 解析流程无法跳出调用循环，必须由
pratt 切断。因此 production 内凡遇 @Expression / pratt 规则一律交回 consume
（pratt 的 binding power + stop_tokens 保证终止）；原子匹配只消费操作数、不
消费运算符（避免 a <= b 赋值 vs 比较歧义）。
"""

from __future__ import annotations

from core.config_registry import ConfigRegistry
from core.define import Token

from .. import LintDiagnostic, token_span
from parser.pratt_parser import install_token_classifier, parse_with_count


class ExpressionChecker:
    """表达式验证器：consume() 返回 (错误列表, 消费数)。"""

    # 递归深度保护：表达式嵌套（SelectSuffix/Concat 内 @Expression）可能病态
    # 递归，超过阈值时截断（仅影响病态输入，正常表达式深度远小于此）。
    _MAX_DEPTH = 40
    _DEPTH = {"n": 0}

    def __init__(self, operator_defs: list, atom_matcher=None) -> None:
        self._op_defs = operator_defs
        # 原子匹配器（共享 RuleMatcher）由 scanner 后置注入：pratt 的原子回调
        # 按 is_atom 规则 production 匹配（参考 parser atomic_rules），不固化。
        self._atom_matcher = atom_matcher
        # pratt 解析依赖 token 分类器（is_number/is_string/...），需安装
        categories = ConfigRegistry._loaded.get("parser.token_categories", {})
        install_token_classifier(categories)

    def set_atom_matcher(self, matcher) -> None:
        """注入共享原子匹配器（RuleMatcher.match_atom，production 驱动）。"""
        self._atom_matcher = matcher

    def _atom_parser(self, tokens: list[Token], idx: int):
        """pratt 的原子解析器回调：交共享原子匹配器，未注入/未命中回退 pratt 内置。"""
        if self._atom_matcher is None:
            return None, 0
        return self._atom_matcher.match_atom(tokens, idx)

    def consume(
        self,
        tokens: list[Token],
        idx: int,
        stop_tokens: set[str] | None = None,
    ) -> tuple[list[LintDiagnostic], int]:
        """从 idx 解析一个表达式。

        Returns:
            (errors, consumed) — 错误列表与消费的 token 数（至少 1）。
        """
        ExpressionChecker._DEPTH["n"] += 1
        if ExpressionChecker._DEPTH["n"] > ExpressionChecker._MAX_DEPTH:
            ExpressionChecker._DEPTH["n"] -= 1
            return [], 1  # 深度保护：仅前进 1 个 token，避免病态递归
        try:
            return self._consume_inner(tokens, idx, stop_tokens)
        finally:
            ExpressionChecker._DEPTH["n"] -= 1

    def _consume_inner(
        self,
        tokens: list[Token],
        idx: int,
        stop_tokens: set[str] | None,
    ) -> tuple[list[LintDiagnostic], int]:
        if idx >= len(tokens):
            return [], 0
        try:
            _, consumed = parse_with_count(
                tokens,
                idx,
                operator_defs=self._op_defs,
                atom_parser=self._atom_parser,
                stop_tokens=stop_tokens,
            )
            if consumed <= 0:
                t = tokens[idx]
                return [
                    LintDiagnostic(
                        range=token_span(t),
                        message=f"expected expression, got '{t.type}'",
                        severity=1,
                        code="phase-expr",
                    )
                ], 1
            return [], consumed
        except ValueError as exc:
            t = tokens[idx]
            return [
                LintDiagnostic(
                    range=token_span(t),
                    message=str(exc),
                    severity=1,
                    code="phase-expr",
                )
            ], 1
        except Exception:
            t = tokens[idx]
            return [
                LintDiagnostic(
                    range=token_span(t),
                    message=f"invalid expression at '{t.content}'",
                    severity=1,
                    code="phase-expr",
                )
            ], 1


