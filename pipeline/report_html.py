"""report_html.py — 时点管线执行轨迹的 HTML 报告（可视化产物的呈现视图）。

吃 `run_pipeline_on_source(...)["trace"]`（ADR-0015 §2 可视化管道：每单元一条
`{index, name, kind, impl?, slot?, params?, requires?, produced?, extra_added,
extra_keys, artifacts?}`），
渲染为单文件 HTML（内联 CSS、零依赖、纯 stdlib）——与 `tpc check --html`
（`analyzer/report_html.py`）同一视觉语言（badge / file 卡片 / table）。

`artifacts` 是插件自述的自由结构（`TransformPlugin.describe()`）→ 本模块只做
**通用值树渲染**（dict/list/标量 → 表格），不认识任何具体键名（不引入
插件/语言知识，见 AGENTS.md 硬约束）。

呈现：顶部**执行管道条**（单元节点链，箭头上标上游产物流；单元自带内部链时
挂为其**子时点**，如 analyze 的 postpass 链）+ 单列**左轴卡片**
（轴节点按 kind 着色，时点顺序显式化）+ 卡片内**依赖行**（requires 机械回指
上游产出该名的单元锚——纯名字匹配，不认识语义）。

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
/* 执行管道条（顶部单元链；箭头上标上游产物流） */
.pipe { display: flex; flex-wrap: wrap; align-items: flex-start; gap: .3rem .45rem;
        margin: .6rem 0 1.3rem; }
.pipe-cell { display: inline-flex; flex-direction: column; gap: .2rem; }
.pipe-node { display: inline-block; padding: .18rem .55rem; border-radius: .4rem;
             font-size: .82rem; font-family: ui-monospace, monospace;
             text-decoration: none; white-space: nowrap; align-self: flex-start; }
.pipe-node:hover { filter: brightness(.93); }
.pipe-arrow { color: #9aa1b5; font-size: .85rem; white-space: nowrap;
              align-self: flex-start; padding-top: .2rem; }
.pipe-arrow small { color: #15803d; font-family: ui-monospace, monospace;
                    margin-left: .2rem; font-size: .78rem; }
/* 子时点（阶段内部链，如 analyze 的 postpass 链）：挂在单元节点下方，可折叠
   注：本块是**普通字符串**（非 raw）——CSS 里别写反斜杠转义（`\25B8` 会被
   Python 当八进制转义吃掉），标记字符直接写字面值。 */
.pipe-sub { margin-left: .35rem; padding-left: .45rem;
            border-left: 2px solid #e3e6f0; }
.pipe-sub > summary { cursor: pointer; list-style: none; }
.pipe-sub > summary::marker { content: ""; }
.pipe-sub > summary::before { content: "▸ "; color: #9aa1b5; }
.pipe-sub[open] > summary::before { content: "▾ "; }
.pipe-sub-label { font-size: .68rem; color: #9aa1b5; letter-spacing: .02em; }
.pipe-sub-list { display: flex; flex-direction: column; gap: .05rem;
                 padding-top: .15rem; }
.pipe-sub-node { font-size: .72rem; color: #555;
                 font-family: ui-monospace, monospace; white-space: nowrap; }
.pipe-sub-node .diag { color: #b45309; margin-left: .3rem; }
/* 单列左轴（时点顺序显式化；节点按 kind 着色） */
.trace { position: relative; padding-left: 2rem; }
.trace::before { content: ""; position: absolute; left: .6rem; top: .4rem;
                 bottom: .4rem; width: 2px; background: #e3e6f0;
                 border-radius: 99px; }
.trace > .file { position: relative; }
.tnode { position: absolute; top: 1.05rem; left: calc(-1.4rem - 5.5px);
         width: 13px; height: 13px; border-radius: 50%; background: #fff;
         border: 3px solid #9aa1b5; box-sizing: border-box; }
.tnode.k-analyze { border-color: #4338ca; }
.tnode.k-transform { border-color: #15803d; }
.tnode.k-check { border-color: #b45309; }
"""


def _esc(v: object) -> str:
    return html.escape(str(v if v is not None else ""))


def _dict_rows_html(value: dict, depth: int) -> str:
    """紧凑键值行（深层 dict 用：depth ≥ 2 时避免"表格套表格"的视觉深度）。"""
    parts = []
    for k, v in value.items():
        parts.append(
            f'<div class="row"><span class="key">{_esc(k)}</span>'
            f"{_value_html(v, depth + 1)}</div>"
        )
    return "".join(parts)


def _dict_table_html(value: dict, depth: int) -> str:
    """dict → 键值表。"""
    rows = []
    for k, v in value.items():
        rows.append(
            f'<tr><td class="key">{_esc(k)}</td><td>{_value_html(v, depth + 1)}</td></tr>'
        )
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def _dict_list_table_html(value: list, depth: int) -> str:
    """同构 dict 列表 → 表头取各元素键的并集。"""
    keys = sorted({k for item in value for k in item})
    rows = []
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


def _value_html(value: object, depth: int = 0) -> str:
    """通用值树 → HTML（dict[键:值] → 表格 / list → 表格或串接 / 标量 → code）。

    不认识任何具体键名（插件自述自由结构），只按类型递归。深层 dict（depth ≥ 2）
    改紧凑键值行（缩进），避免"表格套表格"的视觉深度。
    """
    if isinstance(value, dict):
        if depth >= 2:
            return _dict_rows_html(value, depth)
        return _dict_table_html(value, depth)
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            return _dict_list_table_html(value, depth)
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


def _sub_timepoints_html(entry: dict) -> str:
    """阶段内部链 → 可折叠的**子时点**列表（现唯一来源：analyze 的 `postpasses` 自述）。

    链是单元**内部**的时点序列（见 `analyzer/traversal.py::_run_postpasses`）——
    编号写作 `<index>.<n>`（父单元时点 + 链内序），与卡片里的表同一顺序；
    诊断数只在本环节报过时标出（`+N`）。摘要行给环数与诊断总数，默认**收起**
    （顶层管道条保持紧凑；细看时展开）。不认识具体环节名（通用渲染）。
    """
    records = (entry.get("artifacts") or {}).get("postpasses")
    if not isinstance(records, list) or not records:
        return ""
    idx = entry.get("index", "?")
    total = sum(
        (rec.get("diagnostics") or 0) if isinstance(rec, dict) else 0
        for rec in records
    )
    label = f"postpass 链（子时点）· {len(records)} 环"
    if total:
        label += f" · +{total} 诊断"
    rows = []
    for n, rec in enumerate(records, start=1):
        if isinstance(rec, dict):
            name, diag = rec.get("name", "?"), rec.get("diagnostics")
        else:
            name, diag = rec, None
        diag_html = f'<span class="diag">+{_esc(diag)}</span>' if diag else ""
        rows.append(
            f'<span class="pipe-sub-node">#{_esc(idx)}.{n} {_esc(name)}{diag_html}</span>'
        )
    return (
        f'<details class="pipe-sub">'
        f'<summary class="pipe-sub-label">{_esc(label)}</summary>'
        f'<span class="pipe-sub-list">{"".join(rows)}</span></details>'
    )


def _pipe_html(trace: list[dict]) -> str:
    """执行管道条：单元节点链 + 箭头上标上游产物流（produced，纯机械标签）。

    单元自带内部链（如 analyze 的 postpass 链）→ 挂在节点下方作**子时点**。
    """
    if not trace:
        return ""
    parts = []
    for pos, entry in enumerate(trace):
        if pos:
            upstream = trace[pos - 1].get("produced") or []
            label = (
                f'<small>{_esc(", ".join(str(p) for p in upstream))}</small>'
                if upstream
                else ""
            )
            parts.append(f'<span class="pipe-arrow">&#8594;{label}</span>')
        idx = entry.get("index", "?")
        css = _KIND_CSS.get(str(entry.get("kind", "?")), "sev-info")
        node = (
            f'<a class="pipe-node {css}" href="#unit-{_esc(idx)}">'
            f"#{_esc(idx)} {_esc(entry.get('name', '?'))}</a>"
        )
        subs = _sub_timepoints_html(entry)
        parts.append(
            f'<span class="pipe-cell">{node}{subs}</span>' if subs else node
        )
    return f'<div class="pipe">{"".join(parts)}</div>'


def _deps_row(deps: list[tuple[str, object]]) -> str:
    """依赖行：requires 名 + 上游产出该名的单元链接（None = 未找到）。"""
    items = []
    for rname, producer in deps:
        origin = (
            f'<a href="#unit-{_esc(producer)}">#{_esc(producer)}</a> '
            if producer is not None
            else ""
        )
        items.append(f"{origin}<code>{_esc(rname)}</code>")
    return '<tr><td class="key">依赖</td><td>' + ", ".join(items) + "</td></tr>"


def _code_list(values, empty: str = '<span class="meta">—</span>') -> str:
    """`code` 串接列表（空时占位）。"""
    return ", ".join(f"<code>{_esc(k)}</code>" for k in values) or empty


def _card_meta_rows(entry: dict, deps: list[tuple[str, object]] | None) -> list[str]:
    """卡片元信息行：impl / slot / 依赖 / 产物 / 黑板新增 / 黑板键。"""
    rows = []
    if entry.get("impl"):
        rows.append(
            f'<tr><td class="key">impl</td><td><code>{_esc(entry["impl"])}</code></td></tr>'
        )
    if entry.get("slot"):
        rows.append(f'<tr><td class="key">slot</td><td>{_esc(entry["slot"])}</td></tr>')
    if deps:
        rows.append(_deps_row(deps))
    produced = entry.get("produced") or []
    if produced:
        rows.append(
            '<tr><td class="key">产物</td><td>' + _code_list(produced) + "</td></tr>"
        )
    rows.append(
        '<tr><td class="key">黑板新增</td><td>'
        + _code_list(entry.get("extra_added") or [])
        + "</td></tr>"
    )
    rows.append(
        '<tr><td class="key">黑板键</td><td>'
        + _code_list(entry.get("extra_keys") or [])
        + "</td></tr>"
    )
    return rows


def _unit_card(entry: dict, deps: list[tuple[str, object]] | None = None) -> str:
    """单个加工单元 → 卡片（轴节点 + h2 + 元信息 + 依赖 + 黑板 + artifacts）。

    `deps` = 本单元 requires 名及上游产出该名的单元 index（None = 未找到；
    渲染端只做名字相等匹配，不认识语义）。
    """
    idx = entry.get("index", "?")
    name = _esc(entry.get("name", "?"))
    kind = str(entry.get("kind", ""))
    css = _KIND_CSS.get(kind, "sev-info")
    rows = _card_meta_rows(entry, deps)
    return (
        f'<div class="file" id="unit-{_esc(idx)}">'
        f'<div class="tnode {css}"></div>'
        f'<h2>#{_esc(idx)} {name} '
        f'<span class="badge {css}">{_esc(kind)}</span></h2>'
        f"<table><tbody>{''.join(rows)}</tbody></table>"
        f'{_artifacts_html(entry.get("artifacts") or {})}</div>'
    )


def _kind_counts(trace: list[dict]) -> dict[str, int]:
    """单元按 kind 计数。"""
    counts: dict[str, int] = {}
    for e in trace:
        k = str(e.get("kind", "?"))
        counts[k] = counts.get(k, 0) + 1
    return counts


# 摘要条先列的已知环节（其余 kind 按名字排序补在后）
_SUMMARY_KINDS = ("analyze", "transform", "check")


def _summary_html(trace: list[dict]) -> str:
    """摘要条：单元总数 + 已知环节计数 + 其余 kind 计数。"""
    n_by_kind = _kind_counts(trace)
    summary = [f'<span class="badge ok">{len(trace)} units</span>']
    for k in _SUMMARY_KINDS:
        if n_by_kind.get(k):
            css = _KIND_CSS.get(k, "sev-info")
            summary.append(f'<span class="badge {css}">{k} ×{n_by_kind[k]}</span>')
    for k, n in sorted(n_by_kind.items()):
        if k not in _SUMMARY_KINDS:
            summary.append(f'<span class="badge sev-info">{_esc(k)} ×{n}</span>')
    return "".join(summary)


def _trace_body_html(trace: list[dict]) -> tuple[str, str]:
    """(管道条, 卡片区)。空轨迹 → 空管道 + 提示。"""
    if not trace:
        return "", '<p class="badge sev-warning">trace 为空（管线未执行任何单元）</p>'
    last: dict[str, object] = {}  # 产物名 → 上游产出单元的 index（名字等值匹配）
    cards = []
    for e in trace:
        deps = [(rname, last.get(rname)) for rname in (e.get("requires") or [])]
        cards.append(_unit_card(e, deps))
        for pname in e.get("produced") or []:
            last[pname] = e.get("index")
    return _pipe_html(trace), f'<div class="trace">{"".join(cards)}</div>'


def render_trace_html(
    trace: list[dict],
    *,
    title: str = "tpc pipeline trace",
    source_path: str | None = None,
) -> str:
    """执行轨迹 → 完整 HTML 文档字符串（单文件、内联 CSS、零依赖）。"""
    pipe, body = _trace_body_html(trace)
    meta = (
        f'<div class="meta">source: {_esc(source_path)}</div>' if source_path else ""
    )
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{_esc(title)}</title>"
        f"<style>{REPORT_CSS}{_EXTRA_CSS}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f'<div class="summary">{_summary_html(trace)}</div>'
        f"{meta}{pipe}{body}"
        "</body></html>"
    )
