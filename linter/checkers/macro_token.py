"""checkers/macro_token.py — 非法 token 检查器（迁移原 P0）。

检测 token 流中不应存在的 token 类型（如未展开的宏）。
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic, Position
from .._constants import MACRO_TOKEN_PREFIX
from ..checker import Checker


class MacroTokenChecker(Checker):
    """扫描 token 流，报告未定义宏等非法 token。"""

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end

    def validate(self, tokens: list[Token]) -> list[LintDiagnostic]:
        errors: list[LintDiagnostic] = []
        for idx in range(self.start, min(self.end, len(tokens))):
            t = tokens[idx]
            if t.type.startswith(MACRO_TOKEN_PREFIX):
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"undefined macro '{t.content}'",
                        severity=1,
                        code="undefined-macro",
                    )
                )
        return errors
