"""_tag_check.py — C tag 与枚举常量语义（TAG001/TAG002/ENUM001–003）的 L2 兜底判定。

引擎协议（`analyzer/checks.py::_apply_rule`）：`fn(symbol, rule, context) -> str | None`
（None = 通过；返回消息 = 报诊断，引擎挂 `sym.decl_node` 定位并按 `_interpolate` 插值）。
本 handler 只读**符号 attrs**（包侧 `tag_capture`，见 `grammar/c/plugins/semantics/_api.py::_named_attrs`）
与**同作用域符号表** `symbol.scope.symbols`：

    tag_kind   struct | union | enum（`StructSpecifier.kind.base` / enum 的字面 `default_kind`）
    has_body   该声明是否带体（定义）——缺省 = 引用 / 前向声明
    decl_line / decl_start_line / decl_start_col  声明位置（可见性比较与去重键）

**免误报的两条硬约束**（实测语料 9 条带体定义 + 24 条无体引用）：
  1. TAG001 **只在冲突双方都带体**时报——依据 §6.7.2.3「可见声明存在时该类型说明符不重声明 tag」；
  2. 一切判定都限定在**同一作用域**（`scope.symbols` 只含同作用域首例；第二例与本符号用 `is not`
     区分）——跨作用域同名 tag / 枚举常量是合法的不同类型。

去重：同一 `(规则, 名, 作用域路径)` 只报一次（`context.extra["_tag_seen"]` 记键）——
`struct S{…}; struct S{…}; struct S{…};` 三次定义只出 1 条。

Doc: `grammar/c/README.md`「结构类型语义（TAG/ENUM）」/ 规则表头注（条款引文与档位）
"""
from __future__ import annotations

from typing import Any

from grammar.c.plugins.semantics._api import scope_path

#: 去重键的 `context.extra` 槽位（下划线前缀 = 内部簿记）
_SEEN_KEY = "_tag_seen"


def _attrs(symbol: Any) -> dict:
    return getattr(symbol, "attrs", None) or {}


def _has_body(symbol: Any) -> bool:
    return bool(_attrs(symbol).get("has_body"))


def _tag_kind(symbol: Any) -> str | None:
    val = _attrs(symbol).get("tag_kind")
    return val if isinstance(val, str) and val else None


def _first_of_scope(symbol: Any) -> Any | None:
    """同作用域**首例**符号（不是本符号时返回它；否则 None）。

    语义基座的重名语义是"首见"：`scope.symbols` 不覆盖，第二条声明只进
    `analyzer._all_symbols`（`_api._declare`）⇒ 第二例与首例可用 `is not` 区分。
    """
    scope = getattr(symbol, "scope", None)
    if scope is None:
        return None
    prev = getattr(scope, "symbols", {}).get(symbol.name)
    return prev if prev is not None and prev is not symbol else None


def _line(symbol: Any) -> int | None:
    attrs = _attrs(symbol)
    val = attrs.get("decl_start_line", attrs.get("decl_line"))
    return val if isinstance(val, int) else None


def _visible_complete_enum(symbol: Any) -> bool:
    """作用域链上是否有**可见**的"带体同名 enum"声明（判定 `enum E;` 是否合法）。

    可见性：同作用域的首例必然在前（返回 True）；外层作用域的声明需**声明行 ≤ 本例声明行**
    （作用域始于 tag 出现之后，故后方定义对本例不可见）。行号缺失时保守视为可见（宁漏报不误报）。
    """
    scope = getattr(symbol, "scope", None)
    line = _line(symbol)
    while scope is not None:
        cand = getattr(scope, "symbols", {}).get(symbol.name)
        if cand is not None and cand is not symbol:
            if _tag_kind(cand) == "enum" and _has_body(cand):
                cand_line = _line(cand)
                if line is None or cand_line is None or cand_line <= line:
                    return True
        scope = getattr(scope, "parent", None)
    return False


def _once(context: Any, symbol: Any, rid: str) -> bool:
    """按 `(规则, 名, 作用域路径)` 去重：同一声明组只报一次。"""
    key = (rid, symbol.name, scope_path(getattr(symbol, "scope", None)))
    seen = context.extra.setdefault(_SEEN_KEY, [])
    if not isinstance(seen, list):
        return True
    if key in seen:
        return False
    seen.append(key)
    return True


def check_tag(symbol: Any, rule: dict, context: Any) -> str | None:
    """按 `rule["id"]` 分派判定；返回消息（不过）或 None（通过）。"""
    rid = str(rule.get("id", ""))

    # ── ENUM001 同作用域枚举常量重名（脚注档 ⇒ 默认关）──
    if rid == "ENUM001":
        prev = _first_of_scope(symbol)
        if prev is None or getattr(prev, "kind", None) == "tag":
            return None  # tag 是独立命名空间：同名 tag 不冲突
        if not _once(context, symbol, rid):
            return None
        return (
            f"{symbol.name}: 同一作用域的枚举常量标识符必须互不相同"
            f"（与先前的 {getattr(prev, 'kind', '?')} 声明冲突）"
        )

    # ── ENUM002 反向：普通标识符与同作用域已有枚举常量同名（脚注档 ⇒ 默认关）──
    if rid == "ENUM002":
        prev = _first_of_scope(symbol)
        if prev is None or getattr(prev, "kind", None) != "enumerator":
            return None
        if not _once(context, symbol, rid):
            return None
        return f"{symbol.name}: 与同作用域的枚举常量同名（枚举常量占普通标识符命名空间）"

    # ── 以下三条只对 tag 符号判定 ──
    if getattr(symbol, "kind", None) != "tag":
        return None

    # ── TAG001 同一 tag 的内容至多定义一次（**双方都带体**才算定义）──
    if rid == "TAG001":
        prev = _first_of_scope(symbol)
        if prev is None or getattr(prev, "kind", None) != "tag":
            return None
        if not (_has_body(symbol) and _has_body(prev)):
            return None  # 引用 / 前向声明 + 定义 ⇒ 合法（§6.7.2.3 不重声明 tag）
        if not _once(context, symbol, rid):
            return None
        return f"{symbol.name}: 同一作用域内该 tag 的类型内容至多定义一次（此处为第二次带体定义）"

    # ── TAG002 同一 tag 的多次声明必须同用 struct/union/enum ──
    if rid == "TAG002":
        prev = _first_of_scope(symbol)
        if prev is None or getattr(prev, "kind", None) != "tag":
            return None
        here, before = _tag_kind(symbol), _tag_kind(prev)
        if not here or not before or here == before:
            return None
        if not _once(context, symbol, rid):
            return None
        return (
            f"{symbol.name}: 同一 tag 的声明必须同用 struct / union / enum"
            f"（此前 {before}，此处 {here}）"
        )

    # ── ENUM003 `enum E;`（无枚举列表）只能出现在该类型完整之后 ──
    if rid == "ENUM003":
        if _tag_kind(symbol) != "enum" or _has_body(symbol):
            return None
        if _visible_complete_enum(symbol):
            return None
        if not _once(context, symbol, rid):
            return None
        return f"{symbol.name}: 'enum {symbol.name}' 无枚举列表，只能出现在该类型完整之后"

    return None
