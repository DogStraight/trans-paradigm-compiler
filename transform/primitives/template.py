"""template.py — 模板字符串解析工具

提供 {a.b.c} 模板解析能力，供所有原语复用。
"""

import re
from typing import Any
from core.define import Node

_TEMPLATE_RE = re.compile(r"\{([^}]+)\}")


def lookup_value(path: str, context: dict[str, Any]) -> Any:
    """沿点号/下标路径从 context 取原始值（不做字符串化）。

    与 resolve_template 的区别：复杂值（Node/dict/list）原样返回，
    供 emit 的 ref 透传等需要"拿到对象本身"的场景使用。
    路径解析失败返回 None。
    """
    if path in context:
        return context[path]
    parts = re.split(r"\.|\[|\]", path)
    parts = [p for p in parts if p]
    val: Any = context
    try:
        for p in parts:
            if isinstance(val, dict):
                val = val[p]
            elif isinstance(val, list):
                val = val[int(p)]
            elif hasattr(val, p):
                val = getattr(val, p)
            elif hasattr(val, "__getitem__"):
                val = val[p]
            else:
                return None
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None
    return val


def resolve_template(template: str, context: dict[str, Any]) -> str:
    """解析模板字符串 {attr.sub_attr}，从 context 中取值"""

    def _lookup(path: str, ctx: dict) -> str:
        if path in ctx:
            val = ctx[path]
            return (
                str(val)
                if not isinstance(val, (Node, dict, list))
                else "{" + path + "}"
            )
        parts = re.split(r"\.|\[|\]", path)
        parts = [p for p in parts if p]
        val: Any = ctx
        try:
            for p in parts:
                if isinstance(val, dict):
                    val = val[p]
                elif isinstance(val, list):
                    val = val[int(p)]
                elif hasattr(val, p):
                    val = getattr(val, p)
                elif hasattr(val, "__getitem__"):
                    val = val[p]
                else:
                    return "{" + path + "}"
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            return "{" + path + "}"
        return str(val) if not isinstance(val, (Node, dict, list)) else "{" + path + "}"

    return _TEMPLATE_RE.sub(lambda m: _lookup(m.group(1), context), template)


def resolve_attrs(attrs: Any, context: dict[str, Any]) -> Any:
    """递归解析属性字典/列表中的模板字符串"""
    if isinstance(attrs, str):
        return resolve_template(attrs, context)
    if isinstance(attrs, dict):
        return {k: resolve_attrs(v, context) for k, v in attrs.items()}
    if isinstance(attrs, list):
        return [resolve_attrs(item, context) for item in attrs]
    return attrs
