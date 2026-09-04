"""core/debug_report.py — 失败现场报告工具（parser / linter 共用）。

用途：在"所有路径失效、即将放弃"时生成一份简短的失败现场报告，
记录失败的具体位置 + token 窗口 + 当前失败点信息。回溯解析器中
内层失败是常态（尝试 A 失败回滚试 B），报告只在最终失败时生成
一次，不在回溯路径上逐层打日志——避免大量调试输出刷屏。

Token 需具备 content / type / line / column 属性（parser 与 linter
共用 core.define.Token，字段一致）。
Doc: core/component_protocol.md（失败现场报告）
"""

from __future__ import annotations

from typing import Any


def token_summary(t: Any) -> str:
    """单个 token 的简短摘要。"""
    if t is None:
        return "<EOF>"
    line = getattr(t, "line", "?")
    col = getattr(t, "column", "?")
    return f"{t.content!r}:{t.type}@{line}:{col}"


def format_token_window(
    tokens: list[Any],
    pos: int,
    before: int = 3,
    after: int = 3,
) -> str:
    """格式化 [pos-before, pos+after] 的 token 窗口，标记当前 token。

    前后文（窗口）对"涉及上下文才触发的错误"至关重要——单点 token
    往往无法定位。返回单行紧凑字符串，避免长 token 流刷屏。
    """
    if not tokens:
        return "<empty token stream>"
    start = max(0, pos - before)
    end = min(len(tokens), pos + after + 1)
    parts: list[str] = []
    if start > 0:
        parts.append(f"... ({start} before)")
    for i in range(start, end):
        marker = ">>" if i == pos else "  "
        parts.append(f"{marker}{token_summary(tokens[i])}")
    if end < len(tokens):
        parts.append(f"... ({len(tokens) - end} after)")
    return " | ".join(parts)


def build_failure_report(
    *,
    position: int,
    tokens: list[Any] | None = None,
    reason: str = "",
    rule: str = "",
    path: str = "",
    context: str = "",
    extra: dict | None = None,
    window_before: int = 3,
    window_after: int = 3,
) -> dict:
    """组装失败现场报告（dict 形态，便于打印 / 落盘 / 转诊断）。

    Args:
        position: 失败时的 token 索引。
        tokens:   完整 token 流（用于窗口）。
        reason:   失败原因摘要（"all sentence candidates failed" 等）。
        rule:     失败时正在尝试的规则名。
        path:     语义路径栈（parser）或发现上下文（linter）。
        context:  块/发现上下文名。
        extra:    附加现场信息（match_length、fail_sites 数等）。
    """
    report: dict[str, Any] = {
        "position": position,
        "token": (
            "<EOF>"
            if tokens is None or position >= len(tokens)
            else token_summary(tokens[position])
        ),
        "window": format_token_window(
            tokens or [], position, window_before, window_after
        ),
    }
    if rule:
        report["rule"] = rule
    if path:
        report["path"] = path
    if context:
        report["context"] = context
    if reason:
        report["reason"] = reason
    if extra:
        report["extra"] = extra
    return report


def _ascii_safe(value: Any) -> str:
    """把值转字符串并保证 ASCII：非 ASCII 字符替换为 '?'。

    报告内容（token 内容 / reason 等）可能含中文——Windows 默认 GBK
    控制台无法显示 UTF-8 中文会乱码。渲染层做兜底净化，控制台输出
    必然全 ASCII；程序化访问（_last_failure_report）仍保留原始信息。
    """
    s = str(value)
    try:
        s.encode("ascii")
        return s
    except UnicodeEncodeError:
        return s.encode("ascii", errors="replace").decode("ascii")


def render_failure_report(report: dict) -> str:
    """把报告 dict 渲染为简短多行 ASCII 文本（stderr / 日志用）。

    全部输出 ASCII：中文/块字符在 Windows 默认 GBK 控制台会因 UTF-8
    字节解码错乱而显示乱码，调试输出应跨控制台可读（_ascii_safe 兜底）。
    """
    lines = ["[failure-report] === failure site ==="]
    for k, v in report.items():
        lines.append(f"  {k}: {_ascii_safe(v)}")
    lines.append("[failure-report] ====================")
    return "\n".join(lines)


def reconcile_line_numbers(
    tokens: list[Any], source: str | None = None
) -> list[dict]:
    """行号对账：token.line(1-based) vs token_span(0-based) vs 物理行内容。

    调试用：token.line（lexer/parser 惯例，1-based）与 LSP 的 0-based
    token_span 满足 span0 == line1 - 1。逐 token 列出对账行，并展示物理
    行内容与其是否包含该 token，便于排查多行注释/续行导致的 line 偏移。
    """
    physical = source.splitlines() if source is not None else None
    rows = []
    for i, t in enumerate(tokens):
        line1 = t.line
        physical_line = (
            physical[line1 - 1]
            if physical and 0 <= line1 - 1 < len(physical)
            else None
        )
        rows.append(
            {
                "idx": i,
                "token": token_summary(t),
                "line1": line1,
                "span0": line1 - 1,
                "in_line": (
                    (physical_line.find(t.content) >= 0)
                    if physical_line is not None
                    else None
                ),
                "physical": physical_line,
            }
        )
    return rows


def reconcile_mismatches(tokens: list[Any]) -> list[dict]:
    """返回 line（1-based）非单调递增的 token——行号错位信号。

    正常 token 流 line 应单调不减；回退说明某处（如多行注释）未正确
    更新行号（历史上曾因块注释跨行不更新 line_number 导致连锁错位）。
    """
    bad = []
    prev = 0
    for i, t in enumerate(tokens):
        if t.line < prev:
            bad.append(
                {
                    "idx": i,
                    "line1": t.line,
                    "prev": prev,
                    "token": token_summary(t),
                }
            )
        if t.line > prev:
            prev = t.line
    return bad
