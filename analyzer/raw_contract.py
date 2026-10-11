"""raw_contract.py — raw 节点契约常量 + 语言无关的「类型名查询」注册面。

背景（`docs/gaps/gap-c-semantic-base.md`「机制现状 / 已拍板」）：linter 判"候选不收敛"
后在实体语句位产出 raw 信号 → parser 经过此处**暂缓建树**（产出 raw 节点）→ 分析器
补理解路径。**M2 摘掉诊断后，raw 校验是唯一安全网**——校验不过必须报错，绝不静默。

本模块只放**引擎侧、语言无关**的两样东西：

1. `RawStatement` 节点名与契约字段名（**单一来源**；解析 / 分析 / 渲染三处同源）。
   字段对应冻结契约 A：`raw_names`（歧义标识符，至少首个）/ `raw_line` + `raw_column`
   （use 位置）/ `raw_order`（use 的声明序序号，同行先后不能只靠 line 判）/
   `raw_eligible`（位点是否启用；显式 False ⇒ 不是 raw 位点）。
2. **语言包注册的类型名查询**：`fn(analyzer, context, node, site) -> bool`，`site` =
   `{"name", "scope", "order", "line", "column"}`（`scope` 是引擎算的作用域路径）。
   "哪些 kind 算类型名 / 哪些 kind 属别的命名空间"由语言包在自己那边声明（如 C 包的
   `_p4_query.py`），**引擎不认识任何具体 kind**。

**内建 analyzer 配置**（`BUILTIN_RAW_ANALYZER_CONFIG`）：raw 节点不是任何语言的语法规则
⇒ 规则表里查不到它的 analyzer 配置；`AnalysisTraversal._walk_node` 对该节点名回落到本配置，
保证"raw 校验一定被跑到"——查不到配置就静默跳过 = **安全网静默缺失**（本批最不能出的错）。
Doc: analyzer/semantic_checks.md（原语与 postpass）/ docs/gaps/gap-c-semantic-base.md（P4）
"""
from __future__ import annotations

from typing import Any, Callable

# ── 契约 A1：节点名（引擎侧单一来源） ──────────────────────────────
RAW_STATEMENT_NODE_NAME = "RawStatement"

# ── 契约 A4–A6/A8：字段名（引擎侧单一来源） ────────────────────────
FIELD_NAMES_ATTR = "raw_names"
FIELD_LINE_ATTR = "raw_line"
FIELD_COLUMN_ATTR = "raw_column"
FIELD_ORDER_ATTR = "raw_order"
FIELD_ELIGIBLE_ATTR = "raw_eligible"

#: 校验失败诊断码（语言包可在自己的 analyzer 配置里覆盖）
DEFAULT_ERROR_CODE = "E002"
#: `query` 取该值 = 用当前语言包注册的**唯一**查询（零个或多个 ⇒ 报错，不猜）
QUERY_AUTO = "auto"

#: 校验原语名（规则表配置键；也是原语注册名）
PRIMITIVE_NAME = "validate_raw_statement"

#: 引擎内建 analyzer 配置（raw 节点在规则表里查不到时回落；见模块头注）
BUILTIN_RAW_ANALYZER_CONFIG: dict[str, Any] = {
    PRIMITIVE_NAME: {
        "query": QUERY_AUTO,
        "code": DEFAULT_ERROR_CODE,
    }
}

#: 语言包注册的查询协议：`fn(analyzer, context, node, site) -> bool`
RawNameQuery = Callable[..., bool]

_QUERIES: dict[str, RawNameQuery] = {}


def register_raw_name_query(name: str, fn: RawNameQuery) -> None:
    """语言包注册类型名查询（组件 handler 装载期调用；同名单函数重复注册幂等）。

    重复装载组件会重新 exec handler（`core/plugin_loader` 的模块缓存会拦截，但补注册
    路径仍在），故同名同函数直接复用；同名不同函数视为**替换**（语言包重载更新实现），
    不报错——注册面按语言包单语言选择模型使用。
    """
    if not name or not callable(fn):
        raise ValueError(f"raw 查询注册须为 (name, callable)，实得 {name!r}/{fn!r}")
    _QUERIES[name] = fn


def get_raw_name_query(name: str) -> RawNameQuery | None:
    """按名取查询；`QUERY_AUTO` ⇒ 恰好一个注册项时取之，否则 None（不猜）。"""
    if name == QUERY_AUTO:
        return next(iter(_QUERIES.values())) if len(_QUERIES) == 1 else None
    return _QUERIES.get(name)


def list_raw_name_queries() -> list[str]:
    """已注册查询名（调试 / 测试用）。"""
    return sorted(_QUERIES)


def resolve_raw_name_query(name: str) -> tuple[RawNameQuery | None, str]:
    """`(查询, 失败说明)`：解析不到时给出**可上报**的原因（绝不静默跳过校验）。"""
    query = get_raw_name_query(name)
    if query is not None:
        return query, ""
    if name == QUERY_AUTO:
        return None, (
            f"语言包未注册类型名查询（注册数 {len(_QUERIES)}；需恰好 1 个，"
            f"或在 [RawStatement.analyzer.{PRIMITIVE_NAME}] 里显式声明 query）"
        )
    return None, f"未注册的类型名查询: {name!r}（已注册: {list_raw_name_queries()}）"


def scope_path(scope: Any) -> str:
    """作用域 → 路径字符串（走 `Scope` 骨架自带的 parent 链；引擎通用，无语言知识）。"""
    if scope is None:
        return "<file>"
    names: list[str] = []
    cur = scope
    while cur is not None:
        names.append(getattr(cur, "name", "?"))
        cur = getattr(cur, "parent", None)
    return "/".join(reversed(names))
