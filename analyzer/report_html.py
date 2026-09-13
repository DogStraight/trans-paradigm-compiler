"""report_html.py — tpc check 的 HTML 报告渲染（诊断的另一种视图）。

吃 `ProjectChecker.check()` 的 report dict（files/syntax/semantic/exit_code），
渲染成单文件 HTML 报告（内联 CSS、零依赖、纯 stdlib）——给人看的检查结果
呈现，与 `main.py` 的文本/JSON 输出并列（同吃 report，不同视图）。

severity 约定（与 analyzer 诊断一致）：1=error 2=warning 3=info。
range 为 0-based（LSP 兼容），显示时 +1。
Doc: analyzer/README.md（check HTML 报告）
"""

from __future__ import annotations

import html
import os

# severity → 徽标文案/CSS 类（与 LSP DiagnosticSeverity 对齐）
_SEVERITY_META: dict[int, tuple[str, str]] = {
    1: ("error", "sev-error"),
    2: ("warning", "sev-warning"),
    3: ("info", "sev-info"),
}

# 报告样式（共享给其它报告视图：pipeline/report_html.py 的时点轨迹页）——
# 同一视觉语言（badge / file 卡片 / table），单一样式来源避免重复维护。
REPORT_CSS = """\
:root { color-scheme: light; }   /* 报告元素均为浅色设计：固定浅色，不做深色反转 */
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 2rem;
       max-width: 1000px; background: #fff; color: #1a1a1a; }
h1 { font-size: 1.3rem; }
.summary { display: flex; gap: 1rem; margin: 1rem 0; flex-wrap: wrap; }
.badge { padding: .15rem .6rem; border-radius: 999px; font-size: .85rem; }
.sev-error { background: #fde8e8; color: #b91c1c; }
.sev-warning { background: #fef3c7; color: #b45309; }
.sev-info { background: #e0e7ff; color: #4338ca; }
.ok { background: #dcfce7; color: #15803d; }
.file { border: 1px solid #ddd; border-radius: .5rem; margin: 1rem 0;
        padding: .5rem 1rem; }
.file h2 { font-size: 1rem; font-family: ui-monospace, monospace; margin: .5rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
td, th { border-bottom: 1px solid #eee; padding: .3rem .5rem; vertical-align: top;
         text-align: left; }
td.code { font-family: ui-monospace, monospace; white-space: nowrap; }
.msg { white-space: pre-wrap; }
.related { color: #666; font-size: .85rem; margin-top: .2rem; }
.loc { font-family: ui-monospace, monospace; color: #555; white-space: nowrap; }
.meta { color: #888; font-size: .85rem; margin: .5rem 0; }
"""


def _diag_row(d: dict, path: str) -> str:
    """单条诊断 → HTML 表格行。"""
    sev = _SEVERITY_META.get(d.get("severity", 2), _SEVERITY_META[2])
    label, css = sev
    code = html.escape(str(d.get("code") or ""))
    msg = html.escape(str(d.get("message") or ""))
    r = d.get("range")
    loc = ""
    if r and r.get("start"):
        s = r["start"]
        ln = (s.get("line") or 0) + 1
        col = (s.get("character") or 0) + 1
        loc = f"{os.path.basename(path)}:{ln}:{col}"
    loc_html = f'<span class="loc">{html.escape(loc)}</span>' if loc else ""
    related_html = ""
    for rel in d.get("related", []) or []:
        rl = rel.get("line")
        rpos = ""
        if rl:
            rfile = os.path.basename(rel.get("file") or path)
            rc = rel.get("column") or 0
            rpos = f" — {html.escape(rfile)}:{rl}:{rc}"
        related_html += (
            '<div class="related">↳ '
            + html.escape(str(rel.get("message") or ""))
            + html.escape(rpos)
            + "</div>"
        )
    code_cell = f'<span class="badge {css}">{label}</span> {code}' if code else (
        f'<span class="badge {css}">{label}</span>'
    )
    return (
        "<tr>"
        f'<td class="code">{code_cell}</td>'
        f"<td>{loc_html}<div class=\"msg\">{msg}</div>{related_html}</td>"
        "</tr>"
    )


def render_html_report(report: dict) -> str:
    """ProjectChecker.check() report → 完整 HTML 文档字符串。"""
    files = report.get("files", [])
    n_error = n_warn = n_info = 0
    rows_total = 0
    file_cards = []
    for f in files:
        syntax = f.get("syntax") or []
        semantic = f.get("semantic") or []
        diags = syntax + semantic
        if not diags and f.get("parse_ok", True):
            continue  # 全干净文件不占卡片（与文本输出一致）
        if not diags and not f.get("parse_ok", True):
            n_error += 1  # 纯解析失败文件（无诊断）计一个 error
        rows = []
        for d in diags:
            rows.append(_diag_row(d, f["path"]))
            sev = d.get("severity", 2)
            if sev == 1:
                n_error += 1
            elif sev == 2:
                n_warn += 1
            else:
                n_info += 1
            rows_total += 1
        rel = os.path.relpath(f["path"])
        status = (
            f'<span class="badge ok">parse ok</span>'
            if f.get("parse_ok", True)
            else f'<span class="badge sev-error">parse error</span>'
        )
        parse_err = f.get("parse_error")
        meta = (
            f'<div class="meta">{html.escape(str(parse_err))}</div>'
            if parse_err
            else ""
        )
        body = "".join(rows)
        file_cards.append(
            f'<div class="file"><h2>{html.escape(rel)} {status}</h2>{meta}'
            f"<table><tbody>{body}</tbody></table></div>"
        )
    if rows_total == 0 and not file_cards:
        body_html = '<p class="badge ok">No issues found.</p>'
    else:
        body_html = "".join(file_cards)

    summary = "".join(
        [
            f'<span class="badge sev-error">{n_error} error'
            f"{'s' if n_error != 1 else ''}</span> ",
            f'<span class="badge sev-warning">{n_warn} warning'
            f"{'s' if n_warn != 1 else ''}</span> ",
            f'<span class="badge sev-info">{n_info} info</span>',
        ]
    )
    title = "tpc check report"
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>{REPORT_CSS}</style></head><body>"
        f"<h1>{title}</h1>"
        f'<div class="summary">{summary}</div>'
        f"{body_html}"
        "</body></html>"
    )
