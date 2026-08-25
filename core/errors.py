"""core/errors.py — TransParadigm 统一异常层级。

所有可预期的失败（配置/语法/词法/解析/变换/linter 内部）都继承
TransParadigmError，调用方可按类型捕获并统一处理；未继承该基类的
裸异常说明是未预期的 bug，应让它冒泡而非被吞掉。

分层约定：
    ConfigError        — 配置（tpc_config.json / tpc.toml）加载/解析/验证失败
    GrammarError       — 语法规则（TOML production）定义/加载错误
    LexError           — 词法分析错误
    ParseError         — 解析错误（携带失败上下文字段，见 __init__）
    TransformError     — 变换阶段错误
    LintInternalError  — linter 内部错误（检查器崩溃，转诊断而非静默吞噬）

历史：ParseError 原定义于 core/define.py（纯 Exception），迁移至此纳入统一
层级；core/define.py 保留 re-export，`from core.define import ParseError` 兼容。
Doc: docs/component_protocol.md（引擎异常体系）
"""


class TransParadigmError(Exception):
    """TransParadigm 统一异常基类（管线各阶段可预期失败）。"""


class ConfigError(TransParadigmError):
    """配置（tpc_config.json / tpc.toml）加载/解析/验证失败。"""


class GrammarError(TransParadigmError):
    """语法规则（TOML production）定义/加载错误。"""


class LexError(TransParadigmError):
    """词法分析错误。"""


class TransformError(TransParadigmError):
    """变换阶段错误。"""


class LintInternalError(TransParadigmError):
    """linter 内部错误（检查器崩溃——用于诊断而非静默吞噬）。"""


class ParseError(TransParadigmError):
    """解析错误，携带失败上下文以便快速定位。"""

    def __init__(
        self,
        msg: str = "",
        token=None,
        rule: str | None = None,
        path: str | None = None,
        candidates: list | None = None,
        context_info: str | None = None,
    ):
        self.token = token
        self.rule = rule
        self.path = path
        self.candidates = candidates
        self.context_info = context_info
        parts = [msg]
        if token:
            parts.append(
                f"  token: '{token.content}' (type={token.type}) Ln {token.line}"
            )
        if rule:
            parts.append(f"  rule: {rule}")
        if path:
            parts.append(f"  path: {path}")
        if candidates is not None:
            names = [r.name if hasattr(r, "name") else str(r) for r in candidates]
            parts.append(f"  candidates ({len(candidates)}): {names}")
        if context_info:
            parts.append(f"  ctx: {context_info}")
        super().__init__("\n".join(parts))
