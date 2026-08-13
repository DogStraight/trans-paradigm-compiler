"""PyV Linter — 共享 TOML 语法的轻量错误扫描器。"""

from dataclasses import dataclass, field, asdict

from core.define import Token


@dataclass
class Position:
    """LSP 兼容的位置（0-based）。"""
    line: int
    character: int


@dataclass
class LintDiagnostic:
    """LSP Diagnostic 兼容的错误诊断。"""
    range: tuple[Position, Position]  # (start, end)
    severity: int = 1                 # 1=Error
    code: str = "parse-error"
    source: str = "pyv-lint"
    message: str = ""


def token_pos(t: Token) -> Position:
    """Token → LSP 0-based 单点位置。

    token.line 为 1-based（lexer/parser 惯例，错误消息按 1-based 显示），
    而 LSP Position.line 为 0-based——此处做 1-based→0-based 归一。
    """
    return Position(t.line - 1, t.column)


def token_span(t: Token) -> tuple[Position, Position]:
    """Token → 覆盖整个 token 的 0-based 范围（start..end 含内容宽度）。

    诊断锚定到具体 token 时用 span 而非零宽单点，LSP 下能高亮整个出错
    token，位置更精确。
    """
    return (
        Position(t.line - 1, t.column),
        Position(t.line - 1, t.column + len(t.content)),
    )

    def to_dict(self) -> dict:
        return {
            "range": {
                "start": {"line": self.range[0].line, "character": self.range[0].character},
                "end": {"line": self.range[1].line, "character": self.range[1].character},
            },
            "severity": self.severity,
            "code": self.code,
            "source": self.source,
            "message": self.message,
        }
