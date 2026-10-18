"""preprocessor/macro_timeline.py — 宏定义时间线（调用点可见的形参表）。

**为什么需要**：展开器对**全文件用最终宏表**（历史近似；A1 之前就存在），而 C 的
宏可见性是**顺序的**（§6.10.2：宏自 `#define` 行起生效、`#undef` 后失效、重定义后
按新形参表）。实参个数检查若按最终宏表判，会在"后置定义 / 重定义 / undef"三类形态
上给出与 C 不一致的结论（独立审计实测：`int F(int);` 之后才 `#define F(a, b)` 的
合法文件会被误判成"F(int) 实参个数不符"）。

故扫描期记录**定义/取消事件**（原始源行号 + 形参表；`params=None` = 非函数宏，含
`#undef` 与对象宏定义），检查侧按调用点行号取"不晚于该行的最后一条同名事件"：

    {line: 原始源行号(1-based), name: 宏名, params: list[str] | None}

- 事件表由 `scan_directives(out_macro_events=...)` 产出（`define`/`undef` handler
  写入；`#include` 的内容按"include 行处一次快照"并入宿主，见 include.py）。
- **只覆盖本源文件**：被包含文件内部的定义行属另一坐标系 ⇒ 子扫描不向上传播事件，
  宿主只按 include 行的最终状态记快照。
- 引擎只维护事实，"可见 = 最新一条不晚于该行的事件"是通用语义（与语言包声明的
  宏形态同源），不判语言对错。

Doc: preprocessor/README.md（调用点事实）
"""
from __future__ import annotations

from typing import Any


def params_at(
    events: list[dict[str, Any]], line: int, name: str
) -> list[str] | None:
    """`line`（原始源行，1-based）处 `name` 的可见形参表；非函数宏/未定义 → None。"""
    hit: dict[str, Any] | None = None
    for event in events:
        raw = event.get("line")
        if raw is None or int(raw) > line:
            continue
        if event.get("name") != name:
            continue
        hit = event
    if hit is None:
        return None
    params = hit.get("params")
    return [p for p in params if isinstance(p, str)] if isinstance(params, list) else None


def apply(
    invocations: list[dict[str, Any]],
    events: list[dict[str, Any]] | None,
) -> None:
    """按时间线就地覆写 `params`；调用点当时**不是函数宏** ⇒ 丢弃该条。

    `events` 为 None/空（调用方未提供时间线）⇒ **不动**（保留展开期快照；供只关心
    "调用形态"的调用方使用）。行映射不在此处做（调用方已有 clean→raw 表）。
    """
    if not events:
        return
    kept: list[dict[str, Any]] = []
    for inv in invocations:
        params = params_at(
            events, int(inv.get("line") or 0), str(inv.get("name") or "")
        )
        if params is None:
            continue
        inv["params"] = params
        kept.append(inv)
    invocations[:] = kept
