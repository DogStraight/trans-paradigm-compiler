"""_hier_check.py — 层次引用解析器（hier_check 插件，服务型 postpass）

解析 HierExpr 纯成员链 `a.b.c`（a = 实例，b/c = 被实例化模块的端口或
内部成员）→ 跨模块成员宽度。slang 式按需解析（对标 references.md
「层次引用解析机制调研」：slang Lookup 逐段下钻 instance → body →
member；Verilator VSymGraph 全量 elaboration 对 lint 过重，不做）。

数据全来自 context.extra（module_index/inst 形态）+ analyzer._ast（本
文件 per-module 实例表、节点→模块映射），语言知识（实例/声明/端口节点
形态、参数合并语义）集中本插件层，引擎零硬编码。

消费方：width_check `_hier_width` 查本地宽度表不到时回调
resolve_member_width；direction 供未来跨模块悬空/驱动判定增量。
"""

from core.define import Node

# 实例化节点（本文件/目标模块内的 ModuleInst 均此形态）
_INST_RULE = "ModuleInst"
# 内部成员声明节点（目标模块 node 子树走查）
_DECL_RULES = {"WireDecl", "RegDecl", "IntegerDecl"}
_MODULE_RULES = ("ModuleDecl", "MacroModuleDecl")


def run_hier_check(analyzer, context) -> None:
    """服务型 postpass：建当前文件 per-module 实例表 + 节点→模块映射。

    结果挂 analyzer（_hier_inst_maps / _hier_node_modules），供本文件内
    的层次引用解析 O(1) 查模块归属与实例。无报告——纯服务。
    """
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    analyzer._hier_inst_maps, analyzer._hier_node_modules = _build_maps(root)


def _build_maps(root):
    """{模块名: {实例名: (模块名, site)}} + {id(节点): 模块名}。"""
    inst_maps: dict = {}
    node_modules: dict = {}
    for mod in _iter_nodes(root):
        if mod.node_name not in _MODULE_RULES:
            continue
        mn = _node_text(getattr(mod, "module_name", None))
        if not mn:
            continue
        for n in _iter_nodes(mod):
            node_modules[id(n)] = mn
        insts: dict = {}
        for n in _iter_nodes(mod):
            if n.node_name != _INST_RULE:
                continue
            iname = _node_text(getattr(n, "inst_name", None))
            mname = _node_text(getattr(n, "module_name", None))
            if iname and mname:
                insts.setdefault(iname, (mname, n))
        inst_maps[mn] = insts
    return inst_maps, node_modules


def resolve_member_width(node, analyzer, context) -> int | None:
    """HierExpr 纯成员链 → 跨模块成员宽度（None = 保守不推断）。

    逐段下钻：头段 a 查当前模块实例表 → 目标模块端口表（宽度表达式 +
    实例覆盖参数三层合并）→ 非端口走查目标模块内部声明 → 若本段是目标
    模块内实例再下钻下一段。含下标段（HierSuffix）→ None。
    """
    parts = getattr(node, "parts", None) or []
    if len(parts) < 2:
        return None  # 单段 = 普通信号引用，非层次链
    head = parts[0]
    if not isinstance(head, Node):
        return None
    head_name = getattr(head, "content", "") or ""
    if not head_name:
        return None
    inst_maps = getattr(analyzer, "_hier_inst_maps", None)
    node_modules = getattr(analyzer, "_hier_node_modules", None)
    if inst_maps is None or node_modules is None:
        return None  # hier postpass 未跑（顺序异常）→ 保守
    cur_mod = node_modules.get(id(node))
    if not cur_mod:
        return None
    entry = (inst_maps.get(cur_mod) or {}).get(head_name)
    if entry is None:
        return None  # 头段不是本模块实例（本地信号/未识别 → 保守）
    mod_name, site = entry
    caller_params = _module_defaults(context, cur_mod)
    for part in parts[1:]:
        if not isinstance(part, Node):
            return None
        if part.node_name == "HierSuffix":
            return None  # 下标段（a.b[i]）→ 保守
        pname = _node_text(getattr(part, "name", None))
        if not pname:
            return None
        info = (context.extra.get("module_index", {}) or {}).get(mod_name)
        if info is None:
            return None
        # 端口表命中 → 宽度（端口是成员访问终点）
        port = (getattr(info, "ports", None) or {}).get(pname)
        if port is not None:
            from grammar.verilog.plugins.checks.width_check import _width_check as wc

            params = _merged_params(info, site, caller_params)
            we = getattr(port, "width_expr", None) or ""
            if not we:
                return 1  # 无范围端口 = 标量 1 bit
            return wc.eval_width_text_params(we, params)
        # 内部成员声明命中 → 宽度
        mw = _member_width(info, pname, site, caller_params)
        if mw is not None:
            return mw
        # 本段是目标模块内实例 → 下钻
        sub = _instance_in_module(info, pname)
        if sub is None:
            return None
        mod_name, site = sub
        caller_params = _module_defaults(context, mod_name)
    return None


def _module_defaults(context, mod_name: str) -> dict:
    """模块参数默认值（module_index 参数表 → {名: 值表达式文本}）。"""
    info = (context.extra.get("module_index", {}) or {}).get(mod_name)
    if info is None:
        return {}
    return {p.name: p.value_expr for p in (getattr(info, "params", None) or {}).values()}


def _merged_params(info, site, caller_params: dict) -> dict:
    """B3 三层参数合并：模块默认 → 调用者参数 → 实例覆盖（最高优先）。"""
    out = dict(caller_params)
    # 目标模块默认值（覆盖后未提供时回落）
    for p in (getattr(info, "params", None) or {}).values():
        out.setdefault(p.name, p.value_expr)
    po = getattr(site, "params", None)
    pl = getattr(po, "params", None) if isinstance(po, Node) else None
    items = getattr(pl, "items", None) if isinstance(pl, Node) else None
    for item in items or []:
        if not isinstance(item, Node) or item.node_name != "NamedParamOverride":
            continue
        pn = _node_text(getattr(item, "param_name", None))
        pv = _node_text(getattr(item, "value", None))
        if pn and pv:
            out[pn] = pv
    return out


def _member_width(info, name: str, site, caller_params: dict) -> int | None:
    """目标模块内部成员宽度（走查 ModuleInfo.node 声明子树）。

    类型级/声明符级 packed_range → 文本 → 参数求值；integer → 32。
    """
    node = getattr(info, "node", None)
    if node is None:
        return None
    from grammar.verilog.plugins.checks.width_check import _width_check as wc

    params = _merged_params(info, site, caller_params)
    for n in _iter_nodes(node):
        if n.node_name == "IntegerDecl" and _declares(n, name):
            return 32  # integer = 32 位（IEEE 1364-2005 A.2.1.3）
        if n.node_name not in _DECL_RULES or not _declares(n, name):
            continue
        # 声明符级 packed_range 优先（wire a [7:0]；多声明符按名对齐）
        items = getattr(n, "items", None)
        if isinstance(items, Node):
            for it in getattr(items, "items", None) or []:
                if not isinstance(it, Node):
                    continue
                if getattr(getattr(it, "name", None), "content", "") != name:
                    continue
                w = wc.range_text(getattr(it, "packed_range", None))
                if w:
                    return wc.eval_width_text_params(w, params)
        # 类型级 packed_range（wire [7:0] a）
        w = wc.range_text(getattr(n, "packed_range", None))
        if w:
            return wc.eval_width_text_params(w, params)
        return 1  # 无范围声明 = 标量 1 bit
    return None


def _declares(decl_node: Node, name: str) -> bool:
    """声明节点是否含名为 name 的声明符。"""
    items = getattr(decl_node, "items", None)
    if not isinstance(items, Node):
        return False
    for it in getattr(items, "items", None) or []:
        if isinstance(it, Node) and getattr(getattr(it, "name", None), "content", "") == name:
            return True
    return False


def _instance_in_module(info, name: str):
    """目标模块内名为 name 的实例 → (模块名, site)；无 → None。"""
    node = getattr(info, "node", None)
    if node is None:
        return None
    for n in _iter_nodes(node):
        if n.node_name != _INST_RULE:
            continue
        if _node_text(getattr(n, "inst_name", None)) != name:
            continue
        mname = _node_text(getattr(n, "module_name", None))
        if mname:
            return (mname, n)
    return None


def _node_text(node) -> str:
    """节点 → 源码文本（Identifier 在 content；token 节点 value 递归；
    结构包装（MintypmaxExpr 等）→ children 文本拼接）。"""
    if not isinstance(node, Node):
        return ""
    c = getattr(node, "content", "") or ""
    if c:
        return c
    v = getattr(node, "value", None)
    if isinstance(v, str) and v:
        return v
    if isinstance(v, Node):
        t = _node_text(v)
        if t:
            return t
    parts = []
    for child in node.iter_children():
        t = _node_text(child)
        if t:
            parts.append(t)
    return "".join(parts)


def _iter_nodes(root: Node):
    """DFS 迭代整棵 AST。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.iter_children():
            stack.append(child)
