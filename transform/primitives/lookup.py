"""lookup.py — 查表原语

lookup          从 dict 表中按 key 查找
lookup_scope    从 Scope 作用域链中按名称查找符号
lookup_child_scope  按 kind+名称查找子作用域中的符号
Doc: docs/language_walkthrough.md（查找类变换原语）
"""

from typing import Any
from .template import resolve_template


def lookup(
    table: dict[str, Any],
    key_template: str,
    context: dict[str, Any],
) -> Any:
    """从 table 中查找 key 对应的数据"""
    key = resolve_template(key_template, context)
    parts = key.split(".")
    val: Any = table
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return None
        if val is None:
            return None
    return val


def lookup_scope(
    scope: Any,
    key_template: str,
    context: dict[str, Any],
) -> Any:
    """从 Scope 作用域链中按名称查找符号"""
    key = resolve_template(key_template, context)
    parts = key.split(".")
    sym_name = parts[0]
    attr_path = parts[1:]

    if not hasattr(scope, "resolve"):
        return None
    sym = scope.resolve(sym_name)
    if sym is None:
        return None

    if attr_path:
        val: Any = sym
        for attr in attr_path:
            if hasattr(val, attr):
                val = getattr(val, attr)
            elif isinstance(val, dict) and attr in val:
                val = val[attr]
            else:
                return None
        return val if isinstance(val, (str, int, float, bool, list)) else None

    return {"name": sym.name, "kind": sym.kind, **sym.attrs}


def lookup_child_scope(
    root_scope: Any,
    key_template: str,
    scope_kind: str,
    context: dict[str, Any],
) -> Any:
    """按作用域 kind + 名称查找作用域内符号"""
    key = resolve_template(key_template, context)
    parts = key.split(".")
    if len(parts) < 2:
        return None
    scope_name = parts[0]
    sym_name = parts[1]
    attr_path = parts[2:] if len(parts) > 2 else []

    if not hasattr(root_scope, "find_child_scope"):
        return None

    child_scope = root_scope.find_child_scope(scope_name, scope_kind)
    if child_scope is None:
        return None

    sym = child_scope.resolve(sym_name)
    if sym is None:
        return None

    if attr_path:
        val: Any = sym.attrs
        for attr in attr_path:
            if isinstance(val, dict) and attr in val:
                val = val[attr]
            else:
                return None
        return val

    return {"name": sym.name, "kind": sym.kind, **sym.attrs}
