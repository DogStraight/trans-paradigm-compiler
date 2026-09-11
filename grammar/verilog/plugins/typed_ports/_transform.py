"""typed_ports 组件 — 变换槽位。"""

import hashlib


from core.plugin_loader import register_transform_slot
from core.define import Node
from analyzer.scope import Scope
from transform.engine import mark_extra


@register_transform_slot("delete_type_decl")
def delete_type_decl(node: Node, ctx) -> None:
    del node, ctx  # 槽位协议签名参数，本槽位无操作
    return None


@register_transform_slot("build_wrapper")
def build_wrapper(node: Node, ctx) -> Node | None:
    """从 TypeDecl + TypeImplDecl 构建包装模块。"""
    del node  # 槽位协议签名参数，本槽位从 ctx 取数据
    td = ctx.get("type_decl")
    impl_block = ctx.get("impl_block")
    root_scope: Scope | None = ctx.get("root_scope")
    if not td or not impl_block or not root_scope:
        return None
    type_name = _text(getattr(td, "type_name", None))
    if not type_name:
        return None
    role_name = _first_role_name(root_scope, type_name) or "impl"
    wrapper_name = f"{type_name}_{role_name}"
    ports = _resolved_ports(root_scope, type_name)
    mod = Node("ModuleDecl")
    name_node = Node("Identifier")
    name_node.add_attr("content", wrapper_name)
    mod.add_attr("module_name", name_node)
    # 参数列表
    type_params = getattr(td, "params", None)
    if type_params:
        plp = _make_param_list(type_params)
        if plp:
            mod.add_attr("params", plp)
    # 合并端口
    port_items = []
    if ports:
        for p in ports:
            d = _port_decl(p["direction"], p["name"], p.get("packed_range"))
            if d:
                port_items.append(d)
    impl_ports = getattr(impl_block, "ports", None)
    if impl_ports:
        ipl = getattr(impl_ports, "items", [])
        for ip in ipl:
            if ip.node_name not in ("AnsiInputDecl", "AnsiOutputDecl", "AnsiInoutDecl", "TypedPortDecl"):
                continue
            pname = _port_name(ip)
            if pname and not any(_port_name(pi) == pname for pi in port_items):
                port_items.append(ip)
    if port_items:
        pl = Node("PortList")
        pl.add_attr("items", port_items)
        mod.add_attr("ports", pl)
    # Body
    body = Node("ModuleBlock")
    body.add_attr("sub_node", [])
    impl_body = getattr(impl_block, "body", None)
    if impl_body:
        if isinstance(impl_body, list):
            body.sub_node = [n for n in impl_body if isinstance(n, Node)]
        elif isinstance(impl_body, Node):
            # normalize 把单元素 repeat 展平为单节点（如 body=[WireDecl] → WireDecl），
            # 此时取 sub_node/items 可能得到 DeclaratorList 等非列表 → 需包成列表
            subs = getattr(impl_body, "sub_node", []) or getattr(impl_body, "items", [])
            if isinstance(subs, Node):
                subs = [subs]
            elif not isinstance(subs, list):
                subs = [impl_body]
            body.sub_node = [n for n in subs if isinstance(n, Node)]
    mod.add_attr("body", body)
    mark_extra(wrapper_name, mod)
    return mod


@register_transform_slot("auto_connect_ports")
def auto_connect_ports(node: Node, ctx) -> Node:
    impl = ctx.get("impl_node")
    type_map: dict = ctx.get("type_map", {})
    if not impl or not type_map:
        return node
    iface = getattr(impl, "interface_ref", None)
    if iface is None:
        return node
    iface_name = _text(iface)
    type_name = type_map.get(iface_name, "")
    # 类型 + role 来自 type_spec（如 spi.master → spi / master）
    ts = getattr(impl, "type_spec", None)
    role_name = _text(getattr(ts, "role_name", None)) if ts is not None else ""
    all_ports: list[Node] = []
    explicit_names: set[str] = set()
    explicit = getattr(impl, "ports", None)
    # impl.ports 结构：可能直接是 NamedPortList，也可能包一层
    # （ports.sub_node[0] == NamedPortList，inline ImplPortsParens 未展平）。
    # 统一收敛到 NamedPortConnect 列表。
    conns: list[Node] = []
    _collect_connects(explicit, conns)
    for ep in conns:
        pn = _text(getattr(ep, "port_name", None))
        if pn:
            explicit_names.add(pn)
        all_ports.append(ep)
    if type_name:
        root = ctx.get("root_scope")
        if root:
            resolved = _resolved_ports(root, type_name, role_name=role_name)
            for p in resolved:
                pname = p.get("name", "")
                if not pname or pname in explicit_names:
                    continue
                conn = Node("NamedPortConnect")
                conn.add_attr("port_name", pname)
                sig = Node("Identifier")
                sig.add_attr("content", f"{iface_name}_{pname}")
                conn.add_attr("value", sig)
                all_ports.append(conn)
    if all_ports:
        npl = Node("NamedPortList")
        npl.add_attr("items", all_ports)
        node.add_attr("ports", npl)
    return node


@register_transform_slot("replace_impl_binding")
def replace_impl_binding(node: Node, ctx) -> Node:
    del ctx  # 槽位协议签名参数，本槽位不消费
    ts = getattr(node, "type_spec", None)
    if ts is not None:
        tn = _text(getattr(ts, "type_name", None)) or ""
        rn = _text(getattr(ts, "role_name", None)) or ""
        module_name = f"{tn}_{rn}" if tn and rn else "impl_module"
    else:
        module_name = _text(getattr(node, "module_name", None)) or "impl_module"
    inst_name = _text(getattr(node, "inst_name", None))
    if not inst_name:
        iface = getattr(node, "interface_ref", None)
        salt = module_name
        if iface is not None:
            salt += "_" + _text(iface)
        if ts is not None:
            salt += "_" + _text(getattr(ts, "type_name", None) or "")
            salt += "_" + _text(getattr(ts, "role_name", None) or "")
        inst_name = f"u_{module_name}_" + hashlib.md5(salt.encode()).hexdigest()[:6]
    mi = Node("ModuleInst")
    mi.add_attr("module_name", module_name)
    mi.add_attr("inst_name", inst_name)
    ports = getattr(node, "ports", None)
    if ports is not None:
        mi.add_attr("ports", ports)
    return mi


def _text(n) -> str:
    if isinstance(n, str):
        return n
    if hasattr(n, "content"):
        return n.content
    if hasattr(n, "iter_children"):
        for c in n.iter_children():
            r = _text(c)
            if r:
                return r
    return ""


def _collect_connects(node, out: list[Node]) -> None:
    """递归收集 NamedPortConnect 节点（兼容 ports 的多层包装结构）。

    impl.ports 可能是 NamedPortList 直接、或包一层（sub_node[0] ==
    NamedPortList），也可能嵌套在 items/sub_node 里。递归展开收集。
    """
    if isinstance(node, Node):
        if node.node_name == "NamedPortConnect":
            out.append(node)
            return
        for container in ("items", "sub_node"):
            val = getattr(node, container, None)
            if isinstance(val, Node):
                _collect_connects(val, out)
            elif isinstance(val, list):
                for v in val:
                    _collect_connects(v, out)


def _first_role_name(root_scope, type_name: str) -> str:
    sc = root_scope.find_child_scope(type_name, kind="type") if root_scope else None
    if sc is None:
        return ""
    for sym in sc.symbols.values():
        if sym.kind == "role":
            return sym.name
    return ""


def _make_param_list(type_params) -> Node | None:
    items = getattr(type_params, "items", []) or getattr(type_params, "sub_node", [])
    if not items:
        return None
    param_decls = []
    for item in items:
        if not isinstance(item, Node) or item.node_name != "TypeParamItem":
            continue
        name = getattr(item, "name", None)
        default = getattr(item, "default", None)
        if name is None:
            continue
        pd = Node("ParamDecl")
        pd.add_attr("param_name", name)
        if default is not None:
            pd.add_attr("value", default)
        param_decls.append(pd)
    if not param_decls:
        return None
    pl = Node("ParameterList")
    pl.add_attr("params", param_decls)
    return pl


def _port_name(pn) -> str:
    items = getattr(pn, "items", None)
    if items is None:
        return ""
    for dcl in getattr(items, "items", []):
        name = getattr(dcl, "name", None)
        if name:
            return _text(name)
    return ""


def _port_decl(direction: str, name: str, packed_range=None) -> Node | None:
    if not name:
        return None
    cls = {"input": "AnsiInputDecl", "inout": "AnsiInoutDecl"}.get(direction, "AnsiOutputDecl")
    decl = Node(cls)
    decl.add_attr("direction", direction)
    lst = Node("DeclaratorList")
    dcl = Node("Declarator")
    nid = Node("Identifier")
    nid.add_attr("content", name)
    dcl.add_attr("name", nid)
    pr = _to_range_node(packed_range)
    if pr is not None:
        dcl.add_attr("packed_range", pr)
    lst.add_attr("items", [dcl])
    decl.add_attr("items", lst)
    return decl


def _to_range_node(packed_range):
    """把携带的 packed_range 数据重建为 AST Range 节点。

    数据来源是分析器捕获的端口 dict（node_name 形态的纯 JSON 数据），
    复用 emit 的 dict→Node 重建（含 ref 透传/递归），无需语言知识。
    输入已是 Node / 非 dict 时原样/置空处理。
    """
    if packed_range is None:
        return None
    if isinstance(packed_range, Node):
        return packed_range
    if isinstance(packed_range, dict):
        from transform.primitives.node import emit as _emit

        try:
            return _emit(packed_range, {})
        except Exception:  # noqa: BLE001 — 重建失败视为无位宽（防御）
            return None
    return None


def _resolved_ports(root, type_name: str, role_name: str = "") -> list[dict]:
    """解析类型下指定 role 的扁平端口列表（direction + name）。

    role_name 为空时取第一个有端口数据的 role（build_wrapper 兼容行为）；
    指定时精确匹配该 role（auto_connect_ports 需要——impl type.role 连的是该 role 的端口）。
    """
    sc = root.find_child_scope(type_name, kind="type") if root else None
    if sc is None:
        return []
    for sym in sc.symbols.values():
        if sym.kind != "role":
            continue
        if role_name and sym.name != role_name:
            continue
        # resolved_ports = 组件 postpass（_expand_ports）递归展开的完整端口集；
        # 无则回退 raw 声明拍平（健康 role 都有 resolved_ports，含空展开 []）。
        rp = sym.attrs.get("resolved_ports", [])
        if rp:
            return rp
        raw = sym.attrs.get("ports", [])
        flat = []
        for pg in raw:
            d = pg.get("direction", "") if isinstance(pg, dict) else getattr(pg, "direction", "")
            pr = pg.get("packed_range") if isinstance(pg, dict) else None
            items_node = pg.get("items", {}) if isinstance(pg, dict) else getattr(pg, "items", None)
            if not items_node:
                continue
            item_list = items_node.get("items", []) if isinstance(items_node, dict) else getattr(items_node, "items", [])
            for item in item_list:
                name = item.get("name", "") if isinstance(item, dict) else _text(item)
                if name:
                    entry: dict = {"direction": d, "name": name}
                    if pr:
                        entry["packed_range"] = pr
                    flat.append(entry)
        if flat:
            return flat
    return []
