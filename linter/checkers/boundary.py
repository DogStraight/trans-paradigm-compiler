"""checkers/boundary.py — 块边界配对检查器（迁移原 P1）。

扫描 block openers/closers 配对，报告：
    - unmatched  — 无对应开始的结束符
    - mismatched — 结束符与上一个开始符类型不匹配
    - unclosed   — 文件结束时仍有未闭合的块
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic, Position
from ..checker import Checker

# 通用词法常量（语言无关，自包含于引用处）
_TRIVIA = frozenset({"space.fold", "space", "comment", "newline"})


class BoundaryChecker(Checker):
    """在 token 区间内检查块边界配对。"""

    def __init__(
        self,
        start: int,
        end: int,
        block_openers: frozenset[str],
        block_closers: frozenset[str],
        block_pairs: dict[str, set[str]],
    ) -> None:
        self.start = start
        self.end = end
        self._block_openers = block_openers
        self._block_closers = block_closers
        self._block_pairs = block_pairs

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        errors: list[LintDiagnostic] = []
        stack: list[tuple[str, int]] = []
        for idx in range(self.start, min(self.end, len(tokens))):
            t = tokens[idx]
            if t.type in _TRIVIA:
                continue
            if t.type in self._block_openers:
                stack.append((t.type, idx))
                continue
            if t.type not in self._block_closers:
                continue
            if not stack:
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
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
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"mismatched block closer '{t.content}'",
                        severity=1,
                        code="phase1-boundary",
                    )
                )
                continue
        if stack:
            errors.append(
                LintDiagnostic(
                    range=(Position(0, 0), Position(0, 0)),
                    message=f"unclosed block: {len(stack)} unclosed block(s) at EOF",
                    severity=1,
                    code="phase1-boundary",
                )
            )
        return errors
