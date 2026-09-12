"""report_html.py — 时点管线执行轨迹的 HTML 报告（可视化产物的呈现视图）。

吃 `run_pipeline_on_source(...)["trace"]`（ADR-0015 §2 可视化管道：每单元一条
`{index, name, kind, impl?, slot?, extra_added, extra_keys, artifacts?}`），
渲染为单文件 HTML（内联 CSS、零依赖、纯 stdlib）——与 `tpc check --html`
（`analyzer/report_html.py`）同一视觉语言（badge / file 卡片 / table）。

`artifacts` 是插件自述的自由结构（`TransformPlugin.describe()`）→ 本模块只做
**通用值树渲染**（dict/list/标量 → 表格），不认识任何具体键名（不引入
插件/语言知识，见 AGENTS.md 硬约束）。

Doc: pipeline/README.md（时点轨迹报告）
"""

from __future__ import annotations

import html

from analyzer.report_html import REPORT_CSS

# 单元 kind → 徽标 CSS 类（复用 check 报告色板，语义不同的映射）
_KIND_CSS: dict[str, str] = {
    "analyze": "k-analyze",
    "transform": "k-transform",
    "check": "k-check",
}

# 在共享样式上追加 kind 专用色（同色板，不另起视觉语言）
_EXTRA_CSS = """\
.k-analyze { background: #e0e7ff; color: #4338ca; }
.k-transform { background: #dcfce7; color: #15803d; }
.k-check { background: #fef3c7; color: #b45309; }
.badge.k-analyze, .badge.k-transform, .badge.k-check { font-family: ui-monospace, monospace; }
pre.tree { background: #f8f8f8; border: 1px solid #eee; border-radius: .4rem;
           padding: .5rem .7rem; overflow-x: auto; font-size: .85rem; margin: .3rem 0; }
td.key { font-family: ui-monospace, monospace; white-space: nowrap; color: #555; }
.row { margin: .15rem 0; padding-left: .9rem; }
.row > .key { margin-right: .4rem; }
.origin { font-family: ui-monospace, monospace; white-space: pre-wrap; }
"""


def _esc(v: object) -> str:
    return html.escape(str(v if v is not None else ""))


def _value_html(value: object, depth: int = 0) -> str:
    """通用值树 → HTML（dict[键:值] → 表格 / list → 表格或串接 / 标量 → code）。

    不认识任何具体键名（插件自述自由结构），只按类型递归。深层 dict（depth ≥ 2）
    改紧凑键值行（缩进），避免"表格套表格"的视觉深度。
    """
    if isinstance(value, dict):
        if depth >= 2:
            parts = []
            for k, v in value.items():
                parts.append(
                    f'<div class="row"><span class="key">{_esc(k)}</span>'
                    f"{_value_html(v, depth + 1)}</div>"
                )
            return "".join(parts)
        rows = []
        for k, v in value.items():
            rows.append(
                f'<tr><td class="key">{_esc(k)}</td><td>{_value_html(v, depth + 1)}</td></tr>'
            )
        return f"<table><tbody>{''.join(rows)}</tbody></table>"
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            rows = []
            keys = sorted({k for item in value for k in item})
            for item in value:
                cells = "".join(
                    f"<td>{_value_html(item.get(k), depth + 1)}</td>" for k in keys
                )
                rows.append(f"<tr>{cells}</tr>")
            head = "".join(f"<th>{_esc(k)}</th>" for k in keys)
            return (
                f"<table><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        if not value:
            return '<span class="meta">(空)</span>'
        return "<br>".join(_value_html(v, depth + 1) for v in value)
    if isinstance(value, bool):
        return _esc(str(value).lower())
    return f'<span class="origin">{_esc(value)}</span>'


def _artifacts_html(artifacts: dict) -> str:
    """插件自述区（`{插件名: 自由结构}`）。"""
    if not artifacts:
        return ""
    parts = ['<div class="meta">artifacts（插件自述）</div>']
    for plugin_name, info in artifacts.items():
        parts.append(
            f'<div class="file"><h2>{_esc(plugin_name)}</h2>'
            f"{_value_html(info)}</div>"
        )
    return "".join(parts)


def _unit_card(entry: dict) -> str:
    """单个加工单元 → 卡片（h2 + 元信息 + 黑板 + artifacts）。"""
    idx = entry.get("index", "?")
    name = _esc(entry.get("name", "?"))
    kind = str(entry.get("kind", ""))
    css = _KIND_CSS.get(kind, "sev-info")
    rows = []
    if entry.get("impl"):
        rows.append(
            f'<tr><td class="key">impl</td><td><code>{_esc(entry["impl"])}</code></td></tr>'
        )
    if entry.get("slot"):
        rows.append(f'<tr><td class="key">slot</td><td>{_esc(entry["slot"])}</td></tr>')
    added = entry.get("extra_added") or []
    keys = entry.get("extra_keys") or []
    rows.append(
        '<tr><td class="key">黑板新增</td><td>'
        + (", ".join(f"<code>{_esc(k)}</code>" for k in added) or '<span class="meta">—</span>')
        + "</td></tr>"
    )
    rows.append(
        '<tr><td class="key">黑板键</td><td>'
        + (", ".join(f"<code>{_esc(k)}</code>" for k in keys) or '<span class="meta">—</span>')
        + "</td></tr>"
    )
    return (
        f'<div class="file"><h2>#{_esc(idx)} {name} '
        f'<span class="badge {css}">{_esc(kind)}</span></h2>'
        f"<table><tbody>{''.join(rows)}</tbody></table>"
        f'{_artifacts_html(entry.get("artifacts") or {})}</div>'
    )


def render_trace_html(
    trace: list[dict],
    *,
    title: str = "tpc pipeline trace",
    source_path: str | None = None,
) -> str:
    """执行轨迹 → 完整 HTML 文档字符串（单文件、内联 CSS、零依赖）。"""
    n_by_kind: dict[str, int] = {}
    for e in trace:
        k = str(e.get("kind", "?"))
        n_by_kind[k] = n_by_kind.get(k, 0) + 1

    summary = [f'<span class="badge ok">{len(trace)} units</span>']
    for k in ("analyze", "transform", "check"):
        if n_by_kind.get(k):
            css = _KIND_CSS.get(k, "sev-info")
            summary.append(
                f'<span class="badge {css}">{k} ×{n_by_kind[k]}</span>'
            )
    for k, n in sorted(n_by_kind.items()):
        if k not in ("analyze", "transform", "check"):
            summary.append(f'<span class="badge sev-info">{_esc(k)} ×{n}</span>')

    meta = (
        f'<div class="meta">source: {_esc(source_path)}</div>' if source_path else ""
    )
    if trace:
        body = "".join(_unit_card(e) for e in trace)
    else:
        body = '<p class="badge sev-warning">trace 为空（管线未执行任何单元）</p>'
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{_esc(title)}</title>"
        f"<style>{REPORT_CSS}{_EXTRA_CSS}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f'<div class="summary">{"".join(summary)}</div>'
        f"{meta}{body}"
        "</body></html>"
    )
