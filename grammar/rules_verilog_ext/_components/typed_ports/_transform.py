"""typed_ports 组件 — 变换槽位。"""

import hashlib
from core.component_loader import register_transform_slot
from core.define import Node


@register_transform_slot("delete_type_decl")
def delete_type_decl(node: Node, ctx) -> Node | None:
    return None


@register_transform_slot("build_wrapper")
def build_wrapper(node: Node, ctx) -> Node:
    return node


@register_transform_slot("expand_typed_port")
def expand_typed_port(node: Node, ctx) -> Node | None:
    return node


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
    all_ports: list[Node] = []
    explicit_names: set[str] = set()
    explicit = getattr(impl, "ports", None)
    if explicit is not None:
        for ep in (getattr(explicit, "items", []) or getattr(explicit, "sub_node", [])):
            if isinstance(ep, Node) and ep.node_name == "NamedPortConnect":
                pn = _text(getattr(ep, "port_name", None))
                if pn:
                    explicit_names.add(pn)
                all_ports.append(ep)
    if type_name:
        root = ctx.get("root_scope")
        if root:
            resolved = _resolved_ports(root, type_name)
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


def _resolved_ports(root, type_name: str) -> list[dict]:
    sc = root.find_child_scope(type_name, kind="type") if root else None
    if sc is None:
        return []
    for sym in sc.symbols.values():
        if sym.kind != "role":
            continue
        rp = sym.attrs.get("resolved_ports", [])
        if rp:
            return rp
        cbs = sym.attrs.get("_ref_callbacks", [])
        for cb in cbs:
            rp = cb.get("resolved_ports", [])
            if rp:
                return rp
        raw = sym.attrs.get("ports", [])
        flat = []
        for pg in raw:
            d = pg.get("direction", "") if isinstance(pg, dict) else getattr(pg, "direction", "")
            items_node = pg.get("items", {}) if isinstance(pg, dict) else getattr(pg, "items", None)
            if not items_node:
                continue
            item_list = items_node.get("items", []) if isinstance(items_node, dict) else getattr(items_node, "items", [])
            for item in item_list:
                name = item.get("name", "") if isinstance(item, dict) else _text(item)
                if name:
                    flat.append({"direction": d, "name": name})
        if flat:
            return flat
    return []
