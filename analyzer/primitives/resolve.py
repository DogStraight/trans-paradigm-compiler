"""resolve.py — 引用解析原语

原语:
    resolve_refs — 将标记（marker）识别的引用条目用 scope 知识展开为变换回调

所有语言专用标识符由 TOML 配置提供（00_type_decl.toml）。

职责边界：
    - 分析器：scope 域的知识 — 查找目标符号，获取其数据
    - 变换器：实操 — 收到回调后对 AST 做 emit/switch/prefix/invert

Pipeline:
    resolve_name → find_symbol → get_attrs_list
    → for each: match_marker → resolve_one (scope lookup → recurse → build_callback)
    → store to symbol attrs

使用方式（TOML）：
    [RuleName.analyzer]
    primitives = ["resolve_refs"]
    resolve_refs = { refs = [{ marker = "...", ... }] }
"""

from copy import deepcopy
from core.define import Node
from .registry import analyzer_primitive
from ._utils import (
    resolve_name,
    find_symbol_in_scope,
    get_attrs_list,
    match_marker,
    build_context,
    find_child_scope,
    resolve_template,
    push_cycle,
    pop_cycle,
    build_callback,
)


@analyzer_primitive("resolve_refs")
def resolve_refs(analyzer, node: Node, config: dict) -> None:
    """分析器原语：引用解析，产出变换回调

    产出协议（存入 sym.attrs["_ref_callbacks"]）：
        [{
            "kind": "nested" | "invert",     # 引用类型
            "resolved_ports": [...],          # scope 知识：目标符号的原始数据
            # meta 字段由 TOML refs[].meta 声明:
            "prefix": "upstream",            # nested: 实例名前缀
            "source_type": "axis",           # nested: 源类型名
            "source_role": "master",         # 源角色名
        }]

    消费端：SemanticMappingPlugin._apply_refs()
    输出文件：trans_callback/{name}.json
    """
    self_cfg = config.get("resolve_refs", {})
    source_field = self_cfg.get("source", "ports")
    target_field = self_cfg.get("target", "_ref_callbacks")
    name_attr = self_cfg.get("name_attr", "name")
    ref_descs: list = self_cfg.get("refs", [])

    if not ref_descs:
        return

    sym_name = resolve_name(node, name_attr)
    scope = analyzer._current_scope
    sym = find_symbol_in_scope(scope, sym_name)
    if sym is None:
        return
    raw_items = get_attrs_list(sym, source_field)
    if not raw_items:
        return

    callbacks = _collect_callbacks(raw_items, scope, ref_descs)
    if callbacks:
        sym.attrs[target_field] = callbacks


def _collect_callbacks(
    items: list, scope, ref_descs: list
) -> list[dict]:
    """遍历条目，匹配 marker → resolve_one → 收集回调"""
    callbacks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for rd in ref_descs:
            marker = rd.get("marker", "")
            if not match_marker(item, marker):
                continue
            cb = _resolve_one(marker, item, scope, rd)
            if cb:
                callbacks.append(cb)
            break
    return callbacks


def _resolve_one(marker: str, item: dict, scope, rd: dict) -> dict | None:
    """解析单个引用条目

    Pipeline: build_context → 定位作用域 → 查符号 → 读数据 → 递归 → build_callback
    """
    kind = rd.get("kind", marker)
    scope_mode = rd.get("scope_mode", "self")
    ctx = build_context(item, scope)

    if scope_mode == "child":
        key = resolve_template(rd.get("key", ""), ctx)
        role_key = resolve_template(rd.get("role_key", ""), ctx)
        if not key or not role_key:
            return None
        if push_cycle(marker, key + "." + role_key):
            return None
        try:
            target_scope = find_child_scope(scope, key, rd.get("scope_kind", ""))
            if target_scope is None:
                return None
            target_sym = find_symbol_in_scope(target_scope, role_key)
            if target_sym is None:
                return None
            src = get_attrs_list(target_sym, rd.get("source", "ports"))
            # 递归解析，展平内层回调（防止 kind:invert 等回调混入 resolved_ports）
            resolved = _resolve_and_flatten(src, target_scope, rd.get("refs", []))
            if not resolved:
                resolved = [deepcopy(s) for s in src]
        finally:
            pop_cycle()

    else:  # scope_mode == "self"
        role_key = resolve_template(rd.get("role_key", ""), ctx)
        if not role_key:
            return None
        if push_cycle(marker, (getattr(scope, "name", "?") + "." + role_key)):
            return None
        try:
            target_sym = find_symbol_in_scope(scope, role_key)
            if target_sym is None:
                return None
            src = get_attrs_list(target_sym, rd.get("source", "ports"))
            resolved = _collect_callbacks(src, scope, rd.get("refs", []))
            if not resolved:
                resolved = [deepcopy(s) for s in src]
        finally:
            pop_cycle()

    return build_callback(kind, resolved, rd.get("meta", {}), ctx)


def _resolve_and_flatten(
    items: list, scope, ref_descs: list
) -> list[dict]:
    """递归解析引用，展平回调→扁平端口数据

    与 _collect_callbacks 的区别：不保留回调结构（kind/resolved_ports），
    而是提取 resolved_ports 展开到结果列表。用于 scope_mode="child"
    场景中，确保目标角色的端口数据是纯端口列表，不含嵌套回调。
    """
    result = []
    callbacks = _collect_callbacks(items, scope, ref_descs)
    for cb in callbacks:
        if isinstance(cb, dict) and "resolved_ports" in cb:
            result.extend(deepcopy(cb["resolved_ports"]))
        else:
            result.append(deepcopy(cb))
    return result
