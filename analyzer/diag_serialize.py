"""diag_serialize.py — 诊断 → LSP 形状序列化（check report 的两阶段产出）。

`tpc check` 的 report 是 CLI 与编辑器共同消费的**稳定形状**：每条诊断带 `stage`
（syntax / semantic）、`range`（LSP 0-based）、可选的 `macro`（宏归因）与
`related`（联动链）。这层与"怎么检查"正交，且全部是纯函数（输入 `FileResult`
+ 诊断对象 → dict），故不住在 `ProjectChecker`（门面只做阶段编排与汇总）。

**行号回源**：语法/语义阶段的坐标是*展开后*坐标（宏展开会引入偏移），
`FileResult.line_map` 是展开坐标 → 原始源坐标的复合表（见 `_expand_source`）。
无表 / 越界 / 跨文件节点一律**保留展开行号**——映射可能不准时宁保留诚实偏移，
不给错误的源行号。

Doc: analyzer/semantic_checks.md（跨文件语义检查）
"""

from __future__ import annotations

from analyzer.structure import FileResult


# ── 行号/宏归因 ──────────────────────────────────────────


def map_diag_line(fr: FileResult, line0: int | None) -> int | None:
    """展开坐标（0-based）→ 原始源坐标（0-based）；无表/不可映射时原样保留。

    行表来自 ``_expand_source`` 的两级复合（展开→clean→原始）；None/越界
    一律回退展开行号——映射可能不准时宁保留诚实偏移，不给错误的源行号。
    """
    lm = fr.line_map
    if not lm or line0 is None or not (0 <= line0 < len(lm)):
        return line0
    src = lm[line0]
    return src - 1 if src is not None else line0


def macro_of_line(fr: FileResult, line0: int | None) -> str:
    """诊断行（展开坐标 0-based）落在某宏展开区间 → 宏名；否则空串。

    区间表由 `_expand_source` 在语义展开时换算（展开行区间 + 宏调用
    原始行）；未展开/顿路径无表 → 恒空。归因是**行级**的（宏体多行
    则其内诊断均归该宏）。
    """
    if line0 is None or not fr.macro_regions:
        return ""
    line1 = line0 + 1
    for r in fr.macro_regions:
        if r["line_start"] <= line1 <= r["line_end"]:
            return str(r["name"])
    return ""


# ── 两阶段序列化 ──────────────────────────────────────────


def syntax_diag(fr: FileResult, d) -> dict:
    """linter 诊断（stage=syntax）→ LSP 形状。range 直接取 token 跨度。"""
    span = getattr(d, "range", None)
    if span:
        rng = {
            "start": {
                "line": map_diag_line(fr, span[0].line),
                "character": span[0].character,
            },
            "end": {
                "line": map_diag_line(fr, span[1].line),
                "character": span[1].character,
            },
        }
    else:
        rng = None
    out = {
        "stage": "syntax",
        "file": fr.path,
        "severity": getattr(d, "severity", 1),
        "code": getattr(d, "code", "parse-error"),
        "message": d.message,
        "range": rng,
    }
    macro = macro_of_line(fr, span[0].line) if span else ""
    if macro:
        out["macro"] = macro
    return out


def related_diags(fr: FileResult, d) -> list:
    """诊断 related 链 → LSP 形状列表。

    行号回源只对本文件节点做（跨文件节点的行号属另一文件坐标系）；
    回源失败（无行表/越界）保留原行号。
    """
    related = []
    for msg, rnode in d.related:
        rl = getattr(rnode, "_pos_line", None)
        rc = getattr(rnode, "_pos_col", None)
        if rl is not None and getattr(rnode, "_file", None) in (None, fr.path):
            mapped = map_diag_line(fr, rl - 1)
            if mapped is not None:
                rl = mapped + 1
        related.append(
            {
                "message": msg,
                "file": getattr(rnode, "_file", None) or fr.path,
                "line": rl,
                "column": rc,
            }
        )
    return related


def semantic_diag(fr: FileResult, d) -> dict:
    """analyzer 诊断（stage=semantic）→ LSP 形状（含 related 链 + 宏归因）。

    severity 由 `d.level` 映射（error/warning/info → 1/2/3，未知按 warning）；
    range 由节点 `_pos_line`/`_pos_col` 推出（无位置 → range=None）。
    """
    node = d.node
    line = getattr(node, "_pos_line", None)
    col = getattr(node, "_pos_col", None)
    sev = {"error": 1, "warning": 2, "info": 3}.get(d.level, 2)
    # 行号回源：仅对本文件节点用行表（跨文件节点行号属另一文件坐标系）
    same_file = getattr(node, "_file", None) in (None, fr.path)
    if line is not None:
        line0 = (line - 1) if line else 0
        if same_file:
            line0 = map_diag_line(fr, line0)
        rng = {
            "start": {"line": line0, "character": col or 0},
            "end": {"line": line0, "character": (col or 0) + 1},
        }
    else:
        rng = None
    out = {
        "stage": "semantic",
        "file": fr.path,
        "severity": sev,
        "code": d.code or "semantic",
        "message": d.message,
        "level": d.level,
        "range": rng,
    }
    if line is not None and same_file:
        macro = macro_of_line(fr, (line - 1) if line else 0)
        if macro:
            out["macro"] = macro
    related = related_diags(fr, d)
    if related:
        out["related"] = related
    return out
