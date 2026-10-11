"""raw_validate.py — 通用 raw 校验原语（引擎侧、**语言无关**）。

遍历遇到 `RawStatement` 节点即执行（见 `analyzer/raw_contract.py` 的内建 analyzer 配置与
`AnalysisTraversal._walk_node` 的回落）：读契约字段 `raw_names` / `raw_line` / `raw_column` /
`raw_order`，逐名调用**语言包注册的类型名查询**，**不过即 report 报错（绝不静默）**——
M2 摘掉 linter 诊断后，这是唯一安全网。

语言无关边界：本模块不认识任何 kind、也不认识任何具体语言——kind 语义在语言包注册的
查询里；字段名/诊断码可由语言包在 `[RawStatement.analyzer.validate_raw_statement]` 覆盖。
Doc: analyzer/semantic_checks.md（原语）/ docs/gaps/gap-c-semantic-base.md（P4 安全网）
"""
from __future__ import annotations

from typing import Any

from core.define import Node
from analyzer.primitives.registry import register
from analyzer.raw_contract import (
    DEFAULT_ERROR_CODE,
    FIELD_COLUMN_ATTR,
    FIELD_ELIGIBLE_ATTR,
    FIELD_LINE_ATTR,
    FIELD_NAMES_ATTR,
    FIELD_ORDER_ATTR,
    PRIMITIVE_NAME,
    QUERY_AUTO,
    resolve_raw_name_query,
    scope_path,
)


def _string_list(value: Any) -> list[str]:
    """字段值 → 名称列表（契约允许单串或多串；其它类型忽略，不报错）。"""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str) and v]
    return []


def _position_int(value: Any) -> int | None:
    """位置字段 → int 或 None。

    **契约的未知哨兵要归零**：parser 侧对缺失信息写 0 / -1（如 `raw_order = -1`），
    引擎若照数比较会得到"声明在使用之后"的假结论（`-1 < decl_order` 恒不成立）⇒
    把合法 raw 位点全部误报。故位置字段 ≤0、声明序 <0 一律视为**未知**，
    未知时顺序门回落到下一级判据（见 `_p4_query._precedes`）。
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if value > 0 else None


def _order_int(value: Any) -> int | None:
    """声明序字段 → int 或 None（负值/非 int = 未知）。"""
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if value >= 0 else None


@register(PRIMITIVE_NAME)
def validate_raw_statement(analyzer: Any, node: Node, config: dict) -> None:
    """raw 节点校验：`raw_names` 逐个判"此处是不是类型名"，不过即报 error。

    - `raw_eligible` 显式 False ⇒ 该位点本就未启用 raw（不是 raw 位点），跳过；
    - `raw_names` 缺失/为空 ⇒ 无歧义名可校验，跳过；
    - 查询解析不到 ⇒ **报错**（配置/装载问题，安全网缺失，绝不静默）；
    - 查询返回 False ⇒ 每个未通过的名字各报一条 error（不改 AST、不动 linter 诊断）。
    """
    cfg: dict = {}
    if isinstance(config, dict):
        raw_cfg = config.get(PRIMITIVE_NAME)
        if isinstance(raw_cfg, dict):
            cfg = raw_cfg
    context = analyzer._context

    eligible = getattr(node, str(cfg.get("eligible_attr", FIELD_ELIGIBLE_ATTR)), None)
    if eligible is False:
        return

    names = _string_list(getattr(node, str(cfg.get("names_attr", FIELD_NAMES_ATTR)), None))
    if not names:
        return

    code = str(cfg.get("code", DEFAULT_ERROR_CODE))
    query, reason = resolve_raw_name_query(str(cfg.get("query", QUERY_AUTO)))
    if query is None:
        context.report(
            f"raw 校验未执行：{reason}（安全网缺失，按错误上报）",
            code=code,
            level="error",
            node=node,
        )
        return

    site_base = {
        "scope": scope_path(getattr(analyzer, "_current_scope", None)),
        "order": _order_int(getattr(node, str(cfg.get("order_attr", FIELD_ORDER_ATTR)), None)),
        "line": _position_int(getattr(node, str(cfg.get("line_attr", FIELD_LINE_ATTR)), None)),
        "column": _position_int(
            getattr(node, str(cfg.get("column_attr", FIELD_COLUMN_ATTR)), None)
        ),
    }
    if site_base["order"] is None and site_base["line"] is None:
        # 契约 B 要求 raw 位点带精确 (line, column)：两样都不可用时**无法证明**
        # "声明在前"，按错误上报（不是静默放过——放过就是安全网失效）。
        context.report(
            "raw 位点缺少可用位置信息（契约 B 要求精确 line/column），校验无法进行",
            code=code,
            level="error",
            node=node,
        )
        return
    for name in names:
        if not query(analyzer, context, node, {**site_base, "name": name}):
            context.report(
                f"raw 语句中的名称不是类型名: '{name}'",
                code=code,
                level="error",
                node=node,
            )
