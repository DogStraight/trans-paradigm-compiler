"""_utils.py — 分析器原语共享工具函数

本文件提供各原语可复用的通用操作：scope 查找、模板解析、名称提取等。
不包含任何原语注册，只导出纯函数。
"""

import re
from copy import deepcopy
from core.define import Node


def resolve_template(template: str, context: dict) -> str:
    """从 context dict 沿点号路径取值，解析 {a.b.c} 模板"""
    def _lookup(m):
        key = m.group(1)
        val = context
        for part in key.split("."):
            if isinstance(val, dict):
                val = val.get(part, "")
            else:
                return ""
        return str(val) if val is not None else ""
    return re.sub(r"\{([^}]+)\}", _lookup, template)


def resolve_name(node: Node, attr: str) -> str:
    """从节点属性提取名称值（兼容 Node 和 str）"""
    val = getattr(node, attr, None)
    if val is None:
        return ""
    if isinstance(val, Node):
        return getattr(val, "content", str(val))
    return str(val)


def find_symbol_in_scope(scope, name: str):
    """在当前或指定作用域中按名查找符号"""
    if scope is None or not name:
        return None
    return scope.resolve(name)


def get_attrs_list(sym, field: str) -> list:
    """从符号 attrs 中读取列表字段"""
    items = sym.attrs.get(field, []) if sym else []
    return items if isinstance(items, list) else []


def match_marker(item: dict, marker: str) -> bool:
    """检查条目 dict 是否含有 marker key"""
    return isinstance(item, dict) and marker in item


def build_context(item: dict, scope) -> dict:
    """构建模板解析上下文：条目数据 + 作用域名"""
    ctx = dict(item) if isinstance(item, dict) else {}
    if hasattr(scope, "name"):
        ctx["scope_name"] = scope.name
    return ctx


def find_child_scope(scope, name: str, kind: str):
    """沿作用域链向上查找指定 kind 的子作用域"""
    current = scope
    while current is not None:
        cs = current.find_child_scope(name, kind)
        if cs is not None:
            return cs
        current = current.parent
    return None


# ── 循环引用检测栈（模块级状态）──
_resolve_stack: list[tuple[str, str]] = []


def push_cycle(marker: str, target_key: str) -> bool:
    """入栈循环引用检测，返回 True 表示已存在（循环）"""
    pair = (marker, target_key)
    if pair in _resolve_stack:
        print(f"[analyzer] ERROR 循环引用: "
              f"{' → '.join(f'{p[1]}' for p in _resolve_stack + [pair])}")
        return True
    _resolve_stack.append(pair)
    return False


def pop_cycle():
    """出栈循环引用检测"""
    if _resolve_stack:
        _resolve_stack.pop()


def build_callback(kind: str, resolved: list, meta: dict, ctx: dict) -> dict:
    """构建变换回调

    回调数据格式（分析器→变换器的协议）：
        {
            "kind": "nested" | "invert",    # 引用类型
            "resolved_ports": [...],           # scope 知识：目标符号的原始数据
            # meta 字段（由 TOML refs[].meta 声明，透传到变换器）:
            #   nested: { "prefix": "upstream", "source_type": "axis", "source_role": "master" }
            #   invert: { "source_role": "master" }
        }

    分析器产出此回调存入符号 attrs["_ref_callbacks"]，
    变换器（SemanticMappingPlugin._apply_refs）消费后做机械操作（prefix/invert）。
    """
    cb = {"kind": kind, "resolved_ports": resolved}
    for mk, mv in meta.items():
        if isinstance(mv, str) and "{" in mv:
            cb[mk] = resolve_template(mv, ctx)
        elif isinstance(mv, str) and mv in ctx:
            cb[mk] = ctx.get(mv, mv)
        else:
            cb[mk] = mv
    return cb
