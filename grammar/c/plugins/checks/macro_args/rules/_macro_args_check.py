"""_macro_args_check.py — C 函数宏**实参个数**（MAC001）的 postpass 判定。

作者定调（2026-10-17）：宏的**形式化语法**走 linter（AST 前）、**语义级**（实参个数、
需宏表 + 调用点上下文）走**插件侧 check 族**。本文件是后者的判定实现，规则数据
（id/severity/default/message + 条款原文与档位）在隔壁 `rules/macro_args.toml`。

输入面 = 引擎注入的**展开期事实** `CTX_MACRO_INVOCATIONS`（见 `core/_protocol.py`；
引擎只记事实、不判对错）：

    {name, slots, single_empty, params, line, column}
        slots        实参槽数（顶层逗号 + 1；`F()` 也是 1 槽）
        single_empty 单槽时该槽是否**不含预处理 token**（空白/注释算空）
        params       该调用点**时点可见**的形参表（引擎按宏定义时间线过滤：
                     定义前 / `#undef` 后 / 对象宏的同名点不产生事实；重定义
                     前后各按当时形参表。含变参占位；占位写法由语言包
                     `[macro_syntax].variadic_marker` 声明，不在本文件硬编码）
        line/column  **原始源**坐标（1-based 行 / 0-based 列）

判定（A 档，C99+TC §6.10.3；条款引文与 GCC 16.1 对拍见规则表头注）：
  · 非变参宏 n 个形参：合法 iff `slots == n`；n == 0 的**唯一形态**是
    `slots == 1 且 single_empty`（`Z()` 的括号内是空 token 序列 = 0 个实参，
    而 `O()`（n == 1）是 1 个空实参——两者都合法，判据不同）。
  · 变参宏 n 个具名形参：合法 iff `slots >= n`（缺具名实参 = 全档硬错；
    "恰好 n 个、缺变参"是 C99/C11/C17 pedantic 级、C23 起接受 ⇒ 不在本规则内，
    见规则表「不实现」登记）。

诊断位置：调用点替身节点 `_CallSiteNode`（只有位置、无 AST 语义），`_pos_original`
标记 = 位置已是原始源坐标 ⇒ `analyzer/diag_serialize.py` 不再按展开行表回源。

去重：每调用点至多一条（事实表本就逐调用点一条，不另做声明级去重）。

Doc: `grammar/c/README.md`「宏实参个数（MAC）」 / 规则表 `rules/macro_args.toml`
"""
from __future__ import annotations

from typing import Any

from core._protocol import CTX_MACRO_INVOCATIONS

#: 规则 id（规则表里的 id；本组件只消费这一条）
MAC001 = "MAC001"
#: 观测产物键（context.extra；postpass 无条件写——空展开也写，防下游留回退）
PRODUCT_KEY = "c_macro_args"
#: 替身节点的节点名（仅诊断定位用，不是语法结构）
NODE_NAME = "MacroInvocation"


class _CallSiteNode:
    """宏调用点替身节点：只带位置，供 `context.report(node=...)` 定位。

    真实 AST 节点不存在（宏调用在展开期已被替换）⇒ 位置由展开事实直接给
    （**原始源**坐标）。`_pos_original = True` 告知序列化层不要再做
    "展开坐标 → 原始源"的行表映射。
    """

    __slots__ = ("_pos_line", "_pos_col", "_pos_original", "node_name")

    def __init__(self, line: int, column: int) -> None:
        self.node_name = NODE_NAME
        self._pos_line = line
        self._pos_col = column
        self._pos_original = True


def _variadic_marker(rules_dir: str | None) -> str | None:
    """变参占位写法（语言包 `[macro_syntax].variadic_marker`；未声明 → None）。"""
    if not rules_dir:
        return None
    from preprocessor.macro_shape import load_macro_syntax

    decl = load_macro_syntax(rules_dir=rules_dir)
    return decl.variadic_marker if decl is not None else None


def _active_rule(analyzer: Any) -> dict | None:
    """取**已激活**的 MAC001 规则条目（用户配置可关闭/提级；未激活 → None）。"""
    from analyzer.checks import _plugins_dir_of, active_rule_ids
    from core.check_registry import get_check_rules

    if MAC001 not in active_rule_ids(analyzer):
        return None
    for rule in get_check_rules(_plugins_dir_of(analyzer)):
        if rule.get("id") == MAC001:
            return rule
    return None


def _fill(template: Any, display: str, expected: str, given: int) -> str:
    """规则 message 模板填充（规则=数据；未知占位符原样保留）。"""
    tpl = template if isinstance(template, str) and template else display
    return (
        tpl.replace("{name}", display)
        .replace("{expected}", expected)
        .replace("{given}", str(given))
    )


def _judge(inv: dict, marker: str | None) -> tuple[str, int] | None:
    """单调用点判定 → `(形参个数的展示文案, 实参槽数)`；合法 → None。"""
    raw_params = inv.get("params") or []
    params = [p for p in raw_params if isinstance(p, str)]
    slots = int(inv.get("slots") or 0)
    variadic = marker is not None and marker in params
    named = [p for p in params if p != marker]
    if variadic:
        # 变参宏：具名实参一个都不能少（"缺变参"那档是 pedantic/档位相关，不判）
        if slots < len(named):
            return f"至少 {len(named)}", slots
        return None
    n = len(named)
    if n == 0:
        # 零形参宏的合法调用只有 `Z()`（空实参列表；注释算空）
        if slots == 1 and bool(inv.get("single_empty")):
            return None
        return "0", slots
    return (None if slots == n else (str(n), slots))


def run_macro_arg_checks(analyzer: Any, context: Any) -> None:
    """postpass 入口：逐调用点判定，违规报 MAC001（规则未激活 → 只写产物）。"""
    invocations = list(context.extra.get(CTX_MACRO_INVOCATIONS) or [])
    product: dict[str, Any] = {
        "invocations": len(invocations),
        "violations": [],
    }
    # 无条件写产物（空展开也写 []——下游不必留"没有该键"的回退分支）
    context.extra[PRODUCT_KEY] = product
    if not invocations:
        return
    rule = _active_rule(analyzer)
    if rule is None:
        return
    marker = _variadic_marker(getattr(analyzer, "_rules_dir", None))
    severity = str(rule.get("severity", "warning"))
    code = str(rule.get("id", MAC001))
    for inv in invocations:
        if not isinstance(inv, dict):
            continue
        verdict = _judge(inv, marker)
        if verdict is None:
            continue
        expected, given = verdict
        name = str(inv.get("name") or "?")
        line = int(inv.get("line") or 0)
        column = int(inv.get("column") or 0)
        context.report(
            _fill(rule.get("message"), name, expected, given),
            code=code,
            level=severity,
            node=_CallSiteNode(line, column),
        )
        product["violations"].append(
            {
                "name": name,
                "line": line,
                "column": column,
                "expected": expected,
                "given": given,
            }
        )
