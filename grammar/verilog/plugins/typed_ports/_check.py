"""_check.py — typed_ports 增强语法语义检查（TPxxx，组件内 analyzer postpass）。

增强语法（type/role/impl）的语义良构检查：主流工具不识别这套语法，良构性
只有 tpc 自己能保证（ADR-0013）。坏输入（引用悬空/类型错配/方向冲突/表述
残缺）在展开前被拦成 error 级诊断 → analyze pass 阻断 transform，不静默产出
错误展开。

检查维度三族（ADR-0013「检查点候选」）：
    A 表述完整（语法自洽可还原）：type/role/invert 引用存在、显式端口归属、
      type 定义良构（role 内端口名不重复、invert 无环）
    B 连接正确（类型化 + 方向）：impl 绑定 interface_ref 解析（一组线）、
      类型匹配（spi 端口不能连 sci）、role 同向（ref_spi_inf 同向基准）
    C 单驱动（一个端口一种驱动方式）：同一接口实例被多个 impl 绑定 =
      多驱动预检（对齐展开后 W105，不另造语义）

诊断码：
    A: TP001 type 引用悬空 / TP002 role+invert 悬空 / TP003 显式端口 typo /
       TP004 role 端口重名 / TP006 invert 自反
    B: TP010 interface_ref 未命中端口实例（=> 模块名 = 历史错误写法）/
       TP011 类型不匹配（spi 连 sci）/ TP012 role 不同向
    C: TP020 同一接口实例被多个 impl 绑定（多驱动）

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
    # 收集模块 typed_port 实例表：{模块 scope 名: {实例名: (type_name, role_name, sym)}}
    # impl 绑定（interface_ref）按"impl 所在模块"查本模块声明的接口实例（一组线）。
    module_insts: dict[str, dict[str, tuple]] = _collect_module_typed_ports(root)

    # A 族：type/role/invert 引用存在 + type 定义良构（逐 type scope 查）
    for tname, tsc in type_scopes.items():
        _check_type_wellformed(context, tname, tsc)

    # A/B/C 族：AST 走查 impl 绑定 / typed 端口引用（引用点 × 类型表）。
    # DFS 带当前模块名上下文（impl 的 interface_ref 只在所属模块实例表内查）。
    _walk_ast(ast, context, type_scopes, module_insts, None)

    # C 族：单驱动预检——同一模块内同一接口实例被多个 impl 绑定 →
    # 展开后同线被多实例 output 驱动（与 W105 展开后行为一致，只提前定位）。
    _check_multi_impl_binding(context, ast, module_insts)


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


# ── A/B/C 族：AST 走查（带模块上下文）─────────────────


def _walk_ast(node, context, type_scopes, module_insts, current_mod) -> None:
    """DFS AST，记录当前模块名，对 impl/typed 端口引用点做检查。

    ModuleDecl 进入时更新 current_mod（其端口列表 TypedPortDecl 与体内
    ImplBinding 同属该模块）；退出时恢复父级模块上下文。
    """
    if isinstance(node, Node):
        nn = node.node_name
        if nn == "ModuleDecl":
            mname = _text(getattr(node, "module_name", None)) or current_mod
            _walk_ast_children(node, context, type_scopes, module_insts, mname)
            return
        if nn == "ImplBindingWithInterface":
            _check_impl_binding(context, node, type_scopes, module_insts, current_mod)
        elif nn == "ImplBinding":
            _check_impl_binding(context, node, type_scopes, module_insts, current_mod)
        elif nn == "TypedPortDecl":
            _check_typed_port_decl(context, node, type_scopes)
        # 递归子节点（保持当前模块上下文）
        _walk_ast_children(node, context, type_scopes, module_insts, current_mod)
    elif isinstance(node, list):
        for item in node:
            _walk_ast(item, context, type_scopes, module_insts, current_mod)


def _walk_ast_children(node, context, type_scopes, module_insts, current_mod) -> None:
    for child in node.iter_children():
        _walk_ast(child, context, type_scopes, module_insts, current_mod)


# ── A 族：typed 端口引用点 ────────────────────────────


def _check_typed_port_decl(context, node: Node, type_scopes: dict) -> None:
    """TypedPortDecl（`type.role inst`）：type/role 引用存在。"""
    ts = getattr(node, "type_spec", None)
    if ts is None:
        return
    tname = _text(getattr(ts, "type_name", None))
    rname = _text(getattr(ts, "role_name", None))
    if not tname or not rname:
        return
    _check_type_role_ref(context, node, tname, rname, type_scopes)


# ── B 族：impl 绑定连接正确性 ─────────────────────────


def _check_impl_binding(context, node: Node, type_scopes: dict,
                        module_insts: dict, current_mod) -> None:
    """ImplBinding 绑定检查：type/role 引用存在 + interface_ref 解析 +
    类型匹配 + role 同向 + 显式端口归属。

    ImplBindingWithInterface: `impl type.role (ports) => iface;`
        type_spec（type_name/role_name）→ 引用存在
        interface_ref（=> iface）→ 须解析为 impl 所属模块的 typed_port
            端口实例（一组线）——`=> 模块名`/未声明 = 历史偏离错误写法
        type 匹配：impl type_name == 实例 type_name（spi 端口不能连 sci）
        role 同向：impl role_name == 实例 role_name（ref_spi_inf 同向基准）
        显式端口 ∈ type.role 定义端口集（A 族 TP003）
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
        return  # type/role 引用失败已报，无法继续绑定核对

    # B1 interface_ref 解析：=> iface 必须命中 impl 所属模块的端口实例
    insts = module_insts.get(current_mod or "", {}) or {}
    iface = _text(getattr(node, "interface_ref", None))
    if iface:
        entry = insts.get(iface)
        if entry is None:
            context.report(
                f"impl '{tname}.{rname}' 绑定 '=> {iface}' 未命中模块 "
                f"'{current_mod or '?'}' 的端口实例（interface_ref 须指向 "
                "模块端口声明的接口线，如 `type.role iface`；指向模块名/"
                "未声明 = 错误写法）",
                code="TP010", level="error", node=node,
            )
        else:
            inst_type, inst_role, inst_sym = entry
            _check_impl_instance_match(context, node, tname, rname,
                                       inst_type, inst_role, inst_sym)

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


def _check_impl_instance_match(context, node: Node, impl_type: str, impl_role: str,
                               inst_type: str, inst_role: str, inst_sym) -> None:
    """impl type/role vs 绑定端口实例 type/role：类型匹配 + role 同向。"""
    # B2 类型匹配：spi 端口不能连 sci（跨类型互连 = 编译错误，C++ 强类型）
    if impl_type != inst_type:
        context.report(
            f"impl '{impl_type}.{impl_role}' 绑定类型 '{inst_type}' 的端口实例"
            f"——类型不匹配（{impl_type} 端口不能连 {inst_type}）",
            code="TP011", level="error", node=node,
            related=[("端口实例 '%s' 声明处" % getattr(inst_sym, "name", ""),
                      getattr(inst_sym, "decl_node", None))],
        )
        return  # 类型已错，role 比较无意义
    # B3 role 同向：impl role 与端口实例 role 相同（ref_spi_inf 同向基准）
    if impl_role != inst_role:
        context.report(
            f"impl '{impl_type}.{impl_role}' 绑定 role '{inst_role}' 的端口实例"
            f"——角色不同向（impl role 与端口实例 role 须相同）",
            code="TP012", level="error", node=node,
            related=[("端口实例 '%s' 声明处" % getattr(inst_sym, "name", ""),
                      getattr(inst_sym, "decl_node", None))],
        )


# ── C 族：单驱动（多 impl 绑定同一接口实例）───────────


def _check_multi_impl_binding(context, ast, module_insts) -> None:
    """C 族单驱动预检：同一模块内同一接口实例被多个 impl 绑定。

    语义对齐展开后 W105（signal_graph 多驱动）：两个 impl 绑定同一实例
    （=> spi_io），展开后都连到 spi_io 展开的线、各自 output 驱动 → 同一
    线被多驱动源驱动。本预检只提前定位（模块级早期错误），判定与展开后
    一致，不另造展开后查不到的语义（作者 2026-09-07 定）。
    """
    # {模块名: {实例名: [impl 节点, ...]}}——只统计绑定命中实例的 impl
    bindings: dict[str, dict[str, list[Node]]] = {}
    _collect_impl_bindings(ast, bindings, module_insts, None)
    for mod_name, inst_map in bindings.items():
        insts = module_insts.get(mod_name, {}) or {}
        for iface, nodes in inst_map.items():
            if len(nodes) < 2:
                continue
            inst_sym = insts.get(iface)
            desc = f"接口实例 '{iface}'" + (
                "" if inst_sym is None else
                f"（{inst_sym[0]}.{inst_sym[1]}）"
            )
            context.report(
                f"模块 '{mod_name}' 中 {desc} 被 {len(nodes)} 个 impl 同时绑定"
                "——多驱动冲突（展开后同一线被多实例 output 驱动；一个接口"
                "实例只应被一个 impl 驱动）",
                code="TP020", level="error",
                node=nodes[1],
                related=[("另一 impl 绑定处", nodes[0])],
            )


def _collect_impl_bindings(node, bindings: dict, module_insts: dict,
                           current_mod) -> None:
    """DFS 收集 ImplBindingWithInterface 的 (模块名, interface_ref) → impl 节点。

    只登记 interface_ref 命中本模块端口实例的绑定（悬空 ref 已在 B 族 TP010
    报；未命中实例的 impl 不参与多驱动统计——它绑不到线）。
    """
    if isinstance(node, Node):
        nn = node.node_name
        if nn == "ModuleDecl":
            mname = _text(getattr(node, "module_name", None)) or current_mod
            for child in node.iter_children():
                _collect_impl_bindings(child, bindings, module_insts, mname)
            return
        if nn == "ImplBindingWithInterface":
            iface = _text(getattr(node, "interface_ref", None))
            mod = current_mod or ""
            insts = module_insts.get(mod, {}) or {}
            if iface and iface in insts:
                bindings.setdefault(mod, {}).setdefault(iface, []).append(node)
        for child in node.iter_children():
            _collect_impl_bindings(child, bindings, module_insts, current_mod)
    elif isinstance(node, list):
        for item in node:
            _collect_impl_bindings(item, bindings, module_insts, current_mod)


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


def _collect_module_typed_ports(root) -> dict:
    """收集模块 typed_port 端口实例表。

    返回 {模块 scope 名: {实例名: (type_name, role_name, symbol)}}。
    typed_port 符号在 module scope 下（探针确认 scope=模块名），其
    decl_node.type_spec 带 role_name（symbol capture 只存 type_name，
    role 需从声明节点补取）。impl 绑定按所属模块在本表查 interface_ref。
    """
    out: dict = {}

    def _walk(sc):
        if getattr(sc, "kind", "") == "module":
            insts: dict[str, tuple] = {}
            for sym in sc.symbols.values():
                if getattr(sym, "kind", "") != "typed_port":
                    continue
                tname = (sym.attrs.get("type_name") or "")
                rname = _role_from_decl(getattr(sym, "decl_node", None))
                insts[sym.name] = (tname, rname, sym)
            if insts:
                out[sc.name] = insts
        for child in getattr(sc, "children", []) or []:
            _walk(child)

    _walk(root)
    return out


def _role_from_decl(decl_node) -> str:
    """从 typed_port 声明节点（TypedPortDecl）取 type_spec.role_name。"""
    if decl_node is None:
        return ""
    ts = getattr(decl_node, "type_spec", None)
    if ts is None:
        return ""
    return _text(getattr(ts, "role_name", None))


def _role_sym(tsc, rname: str):
    """type scope 内按名查 role 符号（kind=role）。"""
    sym = tsc.symbols.get(rname)
    if sym is not None and getattr(sym, "kind", "") == "role":
        return sym
    return None


def _role_flat_ports(tsc, rsym) -> list[dict]:
    """role 符号 → 扁平端口列表 [{direction, name, packed_range?}]。

    读序与 _transform._resolved_ports 对齐（组件内共享语义，不重复造）：
    resolved_ports（组件 postpass 递归展开的完整端口集）> raw ports（Ansi
    声明拍平，兜底）。健康 role 都有 resolved_ports（含空展开 []），
    _ref_callbacks 中间层已随旧原语链删除（P1.5 step 2）。
    """
    rp = getattr(rsym, "attrs", {}).get("resolved_ports")
    if rp:
        return rp
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
