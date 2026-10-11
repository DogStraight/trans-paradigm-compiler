"""_storage_check.py — C 存储类说明符语义约束（CSC001–CSC012）的 L2 兜底判定。

引擎协议（`analyzer/checks.py::_call_handler`）：`fn(symbol, rule, context) -> str | None`
（返回 None = 通过；返回消息 = 报诊断，引擎统一插值 + 挂 `sym.decl_node` 定位）。
本 handler 只读**符号 attrs**（包侧 capture，见 `grammar/c/plugins/semantics/_api.py::spec_capture`）：

    sc          该声明的存储类短串表（`StorageClass`/`ThreadLocalSpec`/`ThreadLocalC23Spec`/`ConstexprSpec`）
    fs          函数说明符短串表（`FuncSpec`/`NoreturnSpec`）
    is_function 该声明符是否是函数（`FuncSuffix`）
    has_init    该声明符是否带初始化器
    decl_start_line/decl_start_col  声明起点（**按声明去重**的键；多声明符 `a, b` 同键）

**CSC001 禁止朴素计数**（Lead 硬要求）：判定 = 按节点名分类出的 `sc` 表 + **例外表**比对，
故 `static inline int f(void){}`（`sc=[static]`、`fs=[inline]`）不会误报。

去重：同一 `(规则, 声明起点)` 只报一次（`context.extra["_csc_seen"]` 记键），
故 `static extern int a, b;` 只出 1 条诊断。

Doc: `grammar/c/README.md`「存储类语义约束（CSC）」/ 规则表头注（条款引文与档位）
"""
from __future__ import annotations

from typing import Any

#: `_Thread_local` 的两种拼写（c11 大写、c23 小写）
_THREAD_LOCAL_NAMES: tuple[str, ...] = ("_Thread_local", "thread_local")
_TL_SET = frozenset(_THREAD_LOCAL_NAMES)
#: 允许的存储类共现对（C11 §6.7.1p2 的例外从句）：{static|extern} × {两种拼写}，**均为二元组**。
#: ⚠ 必须逐拼写组合（不能把两种拼写并进同一集合——那会造出三元"允许集"，反而把
#: `static _Thread_local` 这类合法形态判成违规；实测踩到过）。
_ALLOWED_PAIRS = tuple(
    frozenset({companion, tl})
    for companion in ("static", "extern")
    for tl in _THREAD_LOCAL_NAMES
)
#: CSC001/CSC002 保守放行的说明符（共现规则未核实；同 `_api.CSC_PERMISSIVE_SPECS`）
_PERMISSIVE = frozenset({"constexpr"})
#: 去重键的 `context.extra` 槽位（下划线前缀 = 内部簿记，不进用户面）
_SEEN_KEY = "_csc_seen"


def _attrs(symbol: Any) -> dict:
    return getattr(symbol, "attrs", None) or {}


def _specs(symbol: Any) -> list[str]:
    val = _attrs(symbol).get("sc")
    return [s for s in val if isinstance(s, str)] if isinstance(val, list) else []


def _fspecs(symbol: Any) -> list[str]:
    val = _attrs(symbol).get("fs")
    return [s for s in val if isinstance(s, str)] if isinstance(val, list) else []


def _is_function(symbol: Any) -> bool:
    return bool(_attrs(symbol).get("is_function"))


def _in_block(symbol: Any) -> bool:
    """符号是否在**块/函数**作用域（非文件域）——走作用域骨架 parent 链，语言中立。"""
    scope = getattr(symbol, "scope", None)
    return scope is not None and getattr(scope, "parent", None) is not None


def _first_of_declaration(context: Any, symbol: Any, rid: str) -> bool:
    """按**声明**去重：同一 (规则, 声明起点) 只判一次（多声明符只报一条）。"""
    attrs = _attrs(symbol)
    key = (rid, attrs.get("decl_start_line"), attrs.get("decl_start_col"))
    seen = context.extra.setdefault(_SEEN_KEY, [])
    if not isinstance(seen, list):
        return True
    if key in seen:
        return False
    seen.append(key)
    return True


def check_storage(symbol: Any, rule: dict, context: Any) -> str | None:
    """按 `rule["id"]` 分派判定；返回消息（不过）或 None（通过）。"""
    rid = str(rule.get("id", ""))
    sc = _specs(symbol)
    fs = _fspecs(symbol)
    sc_set = set(sc)
    is_fn = _is_function(symbol)

    # ── CSC001 至多一个存储类说明符（例外表；禁止朴素计数）──
    if rid == "CSC001":
        if not _first_of_declaration(context, symbol, rid):
            return None
        counted = [s for s in sc if s not in _PERMISSIVE]
        if len(counted) > 1 and frozenset(counted) not in _ALLOWED_PAIRS:
            return f"{symbol.name}: 一条声明至多一个存储类说明符（{'+'.join(counted)}）"
        return None

    # ── CSC002 typedef 不得与其他存储类共现 ──
    if rid == "CSC002":
        if not _first_of_declaration(context, symbol, rid):
            return None
        others = [s for s in sc if s != "typedef" and s not in _PERMISSIVE]
        if "typedef" in sc_set and others:
            return f"{symbol.name}: typedef 不得与其他存储类说明符共现（{'+'.join(others)}）"
        return None

    # ── CSC003 _Thread_local 不得与 auto/register 共现 ──
    if rid == "CSC003":
        if not _first_of_declaration(context, symbol, rid):
            return None
        if (sc_set & _TL_SET) and (sc_set & {"auto", "register"}):
            return f"{symbol.name}: '_Thread_local/thread_local' 不得与 auto/register 共现"
        return None

    # ── CSC004 _Thread_local 用于函数 ──
    if rid == "CSC004":
        if (sc_set & _TL_SET) and is_fn:
            return f"{symbol.name}: '_Thread_local/thread_local' 只能用于对象"
        return None

    # ── CSC007 constexpr 用于函数 ──
    if rid == "CSC007":
        if "constexpr" in sc_set and is_fn:
            return f"{symbol.name}: constexpr 只能用于对象"
        return None

    # ── CSC008 constexpr 无初始化器 ──
    if rid == "CSC008":
        if not _first_of_declaration(context, symbol, rid):
            return None
        if "constexpr" in sc_set and not is_fn and not _attrs(symbol).get("has_init"):
            return f"{symbol.name}: constexpr 声明必须有初始化器"
        return None

    # ── CSC009/CSC010 auto/register 只允许块作用域对象 ──
    if rid in ("CSC009", "CSC010"):
        kw = "auto" if rid == "CSC009" else "register"
        if kw in sc_set and not _in_block(symbol):
            return f"{symbol.name}: {kw} 只允许块作用域对象"
        return None

    # ── CSC011 register 用于函数 ──
    if rid == "CSC011":
        if "register" in sc_set and is_fn:
            return f"{symbol.name}: register 只能用于对象"
        return None

    # ── CSC012 函数说明符用于对象 ──
    if rid == "CSC012":
        if fs and not is_fn:
            return f"{symbol.name}: {'/'.join(sorted(set(fs)))} 只能用于函数声明"
        return None

    return None
