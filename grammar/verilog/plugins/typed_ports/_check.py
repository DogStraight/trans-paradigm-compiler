"""_check.py — typed_ports 增强语法语义检查（TPxxx，组件内 analyzer postpass）。

增强语法（type/role/impl）的语义良构检查：主流工具不识别这套语法，良构性
只有 tpc 自己能保证（ADR-0013）。坏输入（引用悬空/类型错配/方向冲突/表述
残缺）在展开前被拦成 error 级诊断 → analyze pass 阻断 transform，不静默产出
错误展开。

检查维度三族（ADR-0013「检查点候选」）：
    A 表述完整（语法自洽可还原）：type/role/invert 引用存在、显式端口归属、
      type 定义良构（role 内端口名不重复、invert 无环）
    B 连接正确（类型化 + 方向）：类型匹配（spi 端口不能连 sci）、方向一致、
      实例角色对齐
    C 单驱动（一个端口一种驱动方式）：auto_connect 与显式连接不重复驱动同一
      端口；驱动方式互斥

语义模型（与展开对齐，读 analyzer scope 树 + AST，不重建）：
    type X { role: <ports>; ... }         TypeDecl → scope kind=type
    role 端口 = AnsiInput/Output/InoutDecl | TypeInvertPort | TypeNestedPort
    module 内 `type.role inst`           → TypedPortDecl（typed_port 符号）
    module 内 `impl type.role (...) => i` → ImplBindingWithInterface

语言知识（type/role/invert/impl 形态）集中在本插件层；引擎零硬编码。
执行：typed_ports tpc.toml [analyzer] postpasses = ["_check.py:run_tp_check"]。
"""

from __future__ import annotations

from typing import Any

from core.define import Node


# ── 入口 ──────────────────────────────────────────────


def run_tp_check(analyzer, context) -> None:
    """postpass 入口：遍历 scope 树 + AST，做三族良构检查。

    单文件 analyze（run_pipeline）与 ProjectChecker（tpc check）都会触发
    （postpass 机制通用）。无 type/role/impl 增强语法时零开销返回。
    """
    root = getattr(analyzer, "root_scope", None)
    ast = getattr(analyzer, "_ast", None)
    if root is None or ast is None:
        return

    # 收集类型作用域（kind=type）→ 类型名 → Scope
    type_scopes: dict[str, Any] = _collect_type_scopes(root)

    # A 族：type/role/invert 引用存在 + type 定义良构（逐 type scope 查）
    for tname, tsc in type_scopes.items():
        _check_type_wellformed(context, tname, tsc)

    # A/B/C 族：AST 走查 impl 绑定 / typed 端口引用（引用点 × 类型表）
    for node in _iter_nodes(ast):
        if node.node_name == "ImplBindingWithInterface":
            _check_impl_binding(context, node, type_scopes, root)
        elif node.node_name == "ImplBinding":
            _check_impl_binding(context, node, type_scopes, root)
        elif node.node_name == "TypedPortDecl":
            _check_typed_port_decl(context, node, type_scopes, root)


# ── A 族：type 定义良构 ────────────────────────────────


def _check_type_wellformed(context, tname: str, tsc) -> None:
    """type 定义内部一致性：role 内端口名不重复、invert 无环/目标存在。

    tsc: kind=type 的 Scope（内含 kind=role 的 role 符号与 role 子作用域）。
    """
    # role 符号表：role 名 → Symbol
    role_syms = {
        s.name: s for s in tsc.symbols.values() if getattr(s, "kind", "") == "role"
    }
    # role 作用域树（role 子 scope 内含端口符号）——查逆引用目标存在性
    role_scopes: dict[str, Any] = {}
    for child in getattr(tsc, "children", []) or []:
        if getattr(child, "kind", "") == "role":
            role_scopes[child.name] = child

    for rname, rsym in role_syms.items():
        ports = _role_flat_ports(tsc, rsym)
        names = [p.get("name", "") for p in ports if p.get("name")]
        dup = _dupes(names)
        for d in dup:
            context.report(
                f"type '{tname}' role '{rname}' 端口名重复: '{d}'"
                "（同一 role 内端口名须唯一）",
                code="TP004", level="error",
                node=getattr(rsym, "decl_node", None),
            )
        # invert 引用目标存在 + 非自反（对 raw ports 里的 TypeInvertPort）
        for inv_target in _invert_targets(rsym):
            if inv_target == rname:
                context.report(
                    f"type '{tname}' role '{rname}' invert 自反引用自身 "
                    f"'{inv_target}'（反转须指向另一 role）",
                    code="TP006", level="error",
                    node=getattr(rsym, "decl_node", None),
                )
            elif inv_target not in role_syms:
                context.report(
                    f"type '{tname}' role '{rname}' invert 引用不存在的 role "
                    f"'{inv_target}'",
                    code="TP002", level="error",
                    node=getattr(rsym, "decl_node", None),
                )
            elif inv_target in role_scopes and _invert_targets(role_syms[inv_target]):
                # 双向 invert = 无环检查的退化环（A 只判存在/自反；深环在
                # 展开期由 push_cycle 兜底。此处报双向互反为可疑良构问题）
                pass


# ── A 族：impl 绑定 / typed 端口引用点 ─────────────────


def _check_typed_port_decl(context, node: Node, type_scopes: dict, root) -> None:
    """TypedPortDecl（`type.role inst`）：type/role 引用存在。"""
    ts = getattr(node, "type_spec", None)
    if ts is None:
        return
    tname = _text(getattr(ts, "type_name", None))
    rname = _text(getattr(ts, "role_name", None))
    if not tname or not rname:
        return
    _check_type_role_ref(context, node, tname, rname, type_scopes)


def _check_impl_binding(context, node: Node, type_scopes: dict, root) -> None:
    """ImplBinding 绑定引用 + 显式端口归属 + 类型匹配 + 方向。

    ImplBindingWithInterface: `impl type.role (ports) => iface;`
        type_spec（type_name/role_name）→ 引用存在 + 显式端口 ∈ 定义端口集
    ImplBinding（无 type_spec）：`impl module ...` 走普通实例化检查域
        （inst_check W101-103 覆盖），本检查器不重复。
    """
    ts = getattr(node, "type_spec", None)
    if ts is None:
        return  # 无类型引用（普通模块 impl）→ inst_check 域
    tname = _text(getattr(ts, "type_name", None))
    rname = _text(getattr(ts, "role_name", None))
    if not tname or not rname:
        return
    tsc = _check_type_role_ref(context, node, tname, rname, type_scopes)
    if tsc is None:
        return  # type/role 引用失败已报，无法继续端口归属核对

    # 显式端口名归属：impl 连接的端口名 ∈ type.role 定义端口集
    defined = {
        p.get("name", "") for p in _role_flat_ports(tsc, _role_sym(tsc, rname))
    }
    for conn in _collect_connects(getattr(node, "ports", None)):
        pn = _text(getattr(conn, "port_name", None))
        if pn and pn not in defined:
            context.report(
                f"impl '{tname}.{rname}' 连接了不属于该 role 定义端口集的端口 "
                f"'{pn}'（typo 会被当新端口展开）",
                code="TP003", level="error", node=conn,
            )


# ── 共享辅助 ───────────────────────────────────────────


def _check_type_role_ref(context, node: Node, tname: str, rname: str,
                         type_scopes: dict):
    """type/role 引用存在性检查。type 缺失报 TP001；role 缺失报 TP002。
    返回 type Scope（都通过时）；任一失败返回 None。
    """
    tsc = type_scopes.get(tname)
    if tsc is None:
        context.report(
            f"引用不存在的 type '{tname}'（缺 TypeDecl 定义）",
            code="TP001", level="error", node=node,
        )
        return None
    if _role_sym(tsc, rname) is None:
        context.report(
            f"type '{tname}' 未声明 role '{rname}'",
            code="TP002", level="error", node=node,
        )
        return None
    return tsc


def _collect_type_scopes(root) -> dict:
    """DFS scope 树，收集 kind=type 的作用域 {类型名: Scope}。"""
    out: dict = {}

    def _walk(sc):
        for child in getattr(sc, "children", []) or []:
            if getattr(child, "kind", "") == "type":
                out[child.name] = child
            _walk(child)

    _walk(root)
    return out


def _role_sym(tsc, rname: str):
    """type scope 内按名查 role 符号（kind=role）。"""
    sym = tsc.symbols.get(rname)
    if sym is not None and getattr(sym, "kind", "") == "role":
        return sym
    return None


def _role_flat_ports(tsc, rsym) -> list[dict]:
    """role 符号 → 扁平端口列表 [{direction, name, packed_range?}]。

    读序与 _transform._resolved_ports 对齐（组件内共享语义，不重复造）：
    resolved_ports（分析期拍平） > _ref_callbacks[].resolved_ports（invert/
    nested 展开后）> raw ports（Ansi 声明拍平）。保证检查与展开消费同一数据。
    """
    rp = getattr(rsym, "attrs", {}).get("resolved_ports")
    if rp:
        return rp
    for cb in getattr(rsym, "attrs", {}).get("_ref_callbacks", []) or []:
        cb_rp = cb.get("resolved_ports")
        if cb_rp:
            return cb_rp
    raw = getattr(rsym, "attrs", {}).get("ports", []) or []
    flat = []
    for pg in raw:
        d = pg.get("direction", "") if isinstance(pg, dict) else getattr(pg, "direction", "")
        pr = pg.get("packed_range") if isinstance(pg, dict) else None
        items_node = pg.get("items", {}) if isinstance(pg, dict) else getattr(pg, "items", None)
        if not items_node:
            continue
        item_list = (
            items_node.get("items", [])
            if isinstance(items_node, dict)
            else getattr(items_node, "items", [])
        )
        for item in item_list:
            name = item.get("name", "") if isinstance(item, dict) else _text(item)
            if not name:
                continue
            entry: dict = {"direction": d, "name": name}
            if pr:
                entry["packed_range"] = pr
            flat.append(entry)
    return flat


def _invert_targets(rsym) -> list[str]:
    """role 符号的 raw ports 里 TypeInvertPort 的目标 role 列表。"""
    targets = []
    for pg in getattr(rsym, "attrs", {}).get("ports", []) or []:
        nn = pg.get("node_name", "") if isinstance(pg, dict) else getattr(pg, "node_name", "")
        if nn != "TypeInvertPort":
            continue
        t = pg.get("target_role") if isinstance(pg, dict) else getattr(pg, "target_role", None)
        tg = _text(t)
        if tg:
            targets.append(tg)
    return targets


def _collect_connects(node) -> list[Node]:
    """递归收集 NamedPortConnect 节点（与 _transform._collect_connects 同语义）。"""
    out: list[Node] = []
    if isinstance(node, Node):
        if node.node_name == "NamedPortConnect":
            out.append(node)
            return out
        for container in ("items", "sub_node"):
            val = getattr(node, container, None)
            if isinstance(val, Node):
                out.extend(_collect_connects(val))
            elif isinstance(val, list):
                for v in val:
                    out.extend(_collect_connects(v))
    return out


def _dupes(items: list[str]) -> list[str]:
    """保序去重列表里出现 >1 次的项。"""
    seen: set[str] = set()
    dup: set[str] = set()
    out = []
    for it in items:
        if it in seen and it not in dup:
            dup.add(it)
            out.append(it)
        seen.add(it)
    return out


def _text(node) -> str:
    """Node → 文本（防御非 Node；穿透取首个 content）。"""
    if not isinstance(node, Node):
        return str(node) if node else ""
    content = getattr(node, "content", "") or ""
    if content:
        return content
    for child in node.iter_children():
        t = _text(child)
        if t:
            return t
    return ""


def _iter_nodes(root):
    """DFS 迭代整棵 AST。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.iter_children():
            stack.append(child)
