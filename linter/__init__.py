"""TransParadigm Linter — 共享 TOML 语法的轻量错误扫描器。

Doc: linter/linter_architecture.md
"""

from dataclasses import dataclass

from core.define import Token


@dataclass
class Position:
    """LSP 兼容的位置（0-based）。"""
    line: int
    character: int


@dataclass
class LintDiagnostic:
    """LSP Diagnostic 兼容的错误诊断。

    `blocking` 区分两类诊断的消费语义（structure/checker 两个消费面）：

    - True（缺省，语法类）：token 级结构错误（phase-*/boundary/表达式）——
      解析/语义不可靠，消费方跳过语义阶段并计 exit 1；
    - False（卫生/风格类，如 ST 族）：不影响解析的提示（排版/空白）——
      不阻断语义分析、不计失败退出。
    """
    range: tuple[Position, Position]  # (start, end)
    severity: int = 1                 # 1=Error, 2=Warning
    code: str = "parse-error"
    source: str = "tpc-lint"
    message: str = ""
    blocking: bool = True


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


def lsp_diagnostic(d: LintDiagnostic) -> dict:
    """LintDiagnostic → LSP Diagnostic JSON 兼容 dict。"""
    return {
        "range": {
            "start": {"line": d.range[0].line, "character": d.range[0].character},
            "end": {"line": d.range[1].line, "character": d.range[1].character},
        },
        "severity": d.severity,
        "code": d.code,
        "source": d.source,
        "message": d.message,
    }
