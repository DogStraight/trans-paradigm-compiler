"""checkers/boundary.py — 块边界配对检查器（迁移原 P1）。

扫描 block openers/closers 配对，报告：
    - unmatched  — 无对应开始的结束符
    - mismatched — 结束符与上一个开始符类型不匹配
    - unclosed   — 文件结束时仍有未闭合的块
Doc: linter/linter_architecture.md（P1 块/括号边界配对）
"""

from __future__ import annotations

from core.define import Token
from core.token_protocol import TRIVIA_TOKEN_TYPES

from .. import LintDiagnostic, token_span
from ..checker import Checker

# trivia token 集合（引擎 token 协议，单一事实源 core/token_protocol.py）
_TRIVIA = TRIVIA_TOKEN_TYPES


class BoundaryChecker(Checker):
    """在 token 区间内检查块边界配对。"""

    def __init__(
        self,
        start: int,
        end: int,
        block_openers: frozenset[str],
        block_closers: frozenset[str],
        block_pairs: dict[str, set[str]],
        opener_prev_exclude: dict[str, frozenset[str]] | None = None,
    ) -> None:
        self.start = start
        self.end = end
        self._block_openers = block_openers
        self._block_closers = block_closers
        self._block_pairs = block_pairs
        # opener 前驱排除（语法推导）：前驱命中排除集的 opener 是终结形态
        # （如 use lib.cell:config 的 :config）非块起始，不压栈。
        self._opener_prev_exclude = opener_prev_exclude or {}

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        errors: list[LintDiagnostic] = []
        stack: list[tuple[str, int]] = []
        prev: str | None = None
        for idx in range(self.start, min(self.end, len(tokens))):
            t = tokens[idx]
            if t.type in _TRIVIA:
                continue
            if t.type in self._block_openers:
                # 前驱排除（语法推导）：终结形态的 opener（如 use 子句的
                # :config）不压栈——其前驱命中排除集时它不是块起始。
                if prev not in self._opener_prev_exclude.get(t.type, ()):
                    stack.append((t.type, idx))
                prev = t.type
                continue
            if t.type not in self._block_closers:
                prev = t.type
                continue
            if not stack:
                errors.append(
                    LintDiagnostic(
                        range=token_span(t),
                        message=f"unmatched '{t.content}' without block start",
                        severity=1,
                        code="phase1-boundary",
                    )
                )
                continue
            expected_openers = self._block_pairs.get(t.type, set())
            actual, _ = stack.pop()
            if expected_openers and actual not in expected_openers:
                errors.append(
                    LintDiagnostic(
                        range=token_span(t),
                        message=f"mismatched block closer '{t.content}'",
                        severity=1,
                        code="phase1-boundary",
                    )
                )
                continue
        if stack:
            # 锚定到第一个（最外层）未闭合的块 opener，而非文件开头 (0,0)。
            opener_t = tokens[stack[0][1]]
            errors.append(
                LintDiagnostic(
                    range=token_span(opener_t),
                    message=f"unclosed block: {len(stack)} unclosed block(s) at EOF",
                    severity=1,
                    code="phase1-boundary",
                )
            )
        return errors
