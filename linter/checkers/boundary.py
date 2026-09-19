"""checkers/boundary.py — 块边界配对检查器（迁移原 P1）。

扫描 block openers/closers 配对，报告：
    - unmatched  — 无对应开始的结束符
    - mismatched — 结束符与上一个开始符类型不匹配
    - unclosed   — 文件结束时仍有未闭合的块
Doc: linter/linter_architecture.md（P1 块/括号边界配对）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.define import Token
from core.token_protocol import TRIVIA_TOKEN_TYPES

from .. import LintDiagnostic, token_span
from ..checker import Checker

# trivia token 集合（引擎 token 协议，单一事实源 core/token_protocol.py）
_TRIVIA = TRIVIA_TOKEN_TYPES


@dataclass
class _BoundaryScan:
    """边界配对扫描状态。"""

    stack: list[tuple[str, int]] = field(default_factory=list)  # (opener 类型, idx)
    prev: str | None = None                                     # 上一个非 trivia token 类型


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
        """token 区间内块边界配对：unmatched / mismatched / unclosed 三类诊断。"""
        scan = _BoundaryScan()
        errors: list[LintDiagnostic] = []
        for idx in range(self.start, min(self.end, len(tokens))):
            t = tokens[idx]
            if t.type in _TRIVIA:
                continue
            d = self._scan_token(t, idx, scan)
            if d is not None:
                errors.append(d)
        if scan.stack:
            errors.append(_unclosed_diag(tokens, scan.stack))
        return errors

    def _scan_token(
        self, t: Token, idx: int, scan: _BoundaryScan
    ) -> LintDiagnostic | None:
        """单个非 trivia token：opener 压栈 / 普通 token 记前驱 / closer 配对。"""
        if t.type in self._block_openers:
            self._push_opener(t, idx, scan)
            return None
        if t.type not in self._block_closers:
            scan.prev = t.type
            return None
        return self._close_block(t, scan)

    def _push_opener(self, t: Token, idx: int, scan: _BoundaryScan) -> None:
        """opener 压栈并更新前驱。

        前驱排除（语法推导）：终结形态的 opener（如 use 子句的 `:config`）
        不压栈——其前驱命中排除集时它不是块起始。
        """
        if scan.prev not in self._opener_prev_exclude.get(t.type, ()):
            scan.stack.append((t.type, idx))
        scan.prev = t.type

    def _close_block(self, t: Token, scan: _BoundaryScan) -> LintDiagnostic | None:
        """closer 配对：栈空 → unmatched；与栈顶不匹配 → mismatched。

        配对成功（或报 unmatched）时不更新前驱——沿用原实现在 closer
        分支里的前驱处理。
        """
        if not scan.stack:
            return _boundary_diag(t, f"unmatched '{t.content}' without block start")
        expected_openers = self._block_pairs.get(t.type, set())
        actual, _ = scan.stack.pop()
        if expected_openers and actual not in expected_openers:
            return _boundary_diag(t, f"mismatched block closer '{t.content}'")
        return None


def _boundary_diag(t: Token, message: str) -> LintDiagnostic:
    """块边界诊断（severity=1、code=phase1-boundary）。"""
    return LintDiagnostic(
        range=token_span(t),
        message=message,
        severity=1,
        code="phase1-boundary",
    )


def _unclosed_diag(tokens: list[Token], stack: list[tuple[str, int]]) -> LintDiagnostic:
    """unclosed：锚定到第一个（最外层）未闭合的块 opener，而非文件开头 (0,0)。"""
    return _boundary_diag(
        tokens[stack[0][1]],
        f"unclosed block: {len(stack)} unclosed block(s) at EOF",
    )
