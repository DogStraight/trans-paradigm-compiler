"""PyV Linter — 共享 TOML 语法的轻量错误扫描器。"""

from dataclasses import dataclass, field, asdict


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
