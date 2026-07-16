"""component_bridge.py — 组件变换桥接插件

将组件中注册的 transform 槽位包装为 TransformPlugin，
注册到 AstTransformer 管线。
"""

from typing import Any, Optional
from core.define import Node, Token
from analyzer.scope import Scope
from transform.pipeline import TransformPlugin, register_plugin, mark_extra


def _get_slots():
    """懒加载组件槽位，避免 import 时循环依赖。"""
    from core.component_loader import get_transform_slots
    return get_transform_slots()


@register_plugin
class ComponentSlotPlugin(TransformPlugin):
    """将组件的 transform 槽位作为 TransformPlugin 运行。

    本插件遍历 AST，对每个节点检查是否有对应槽位名称的规则配置，
    若有则调用槽位处理函数。
    """

    def __init__(self):
        self._root_scope: Optional[Scope] = None
        self._type_map: dict[str, str] = {}
        self._stats = {"slots_called": 0}

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def process(self, ast: Node, root_scope: Scope) -> Node:
        self._root_scope = root_scope
        slots = _get_slots()
        if not slots:
            return ast

        # 第〇阶段：扫描 TypedPortDecl 建类型映射
        self._scan_typed_ports(ast)

        # 第一阶段：Root.sub_node 中的 TypeDecl → 包装模块 + 删除
        ast = self._process_type_decls(ast, slots)

        # 第二阶段：递归替换 ImplBinding
        ast = self._process_impls(ast, slots)

        return ast

    def _scan_typed_ports(self, node: Node) -> None:
        if node.node_name == "TypedPortDecl":
            ts = getattr(node, "type_spec", None)
            inst = getattr(node, "instance_name", None)
            if ts and inst:
                tn = _node_text(getattr(ts, "type_name", None))
                iname = _node_text(getattr(inst, "name", None))
                if tn and iname:
                    self._type_map[iname] = tn
        for c in node.iter_children():
            self._scan_typed_ports(c)

    def _process_type_decls(self, root: Node, slots: dict) -> Node:
        subs = getattr(root, "sub_node", [])
        remaining = []
        for node in subs:
            if node.node_name == "TypeDecl":
                impl_block = self._find_type_impl(node)
                if impl_block:
                    ctx = {
                        "type_decl": node,
                        "impl_block": impl_block,
                        "root_scope": self._root_scope,
                        "role_name": None,
                    }
                    # 直接调用 impl_wrapper 逻辑生成包装模块
                    wrapper = self._build_wrapper(node, impl_block)
                    if wrapper:
                        self._stats["slots_called"] += 1
                # 删除 TypeDecl
                dd = slots.get("delete_type_decl")
                if dd:
                    dd(node, {})
                    self._stats["slots_called"] += 1
            else:
                remaining.append(node)
        root.sub_node = remaining
        return root

    def _find_type_impl(self, td: Node) -> Optional[Node]:
        body = getattr(td, "body", None)
        if body is None:
            return None
        members = getattr(body, "members", None)
        if members is None:
            return None
        if isinstance(members, Node):
            subs = getattr(members, "sub_node", []) or getattr(members, "items", [])
        elif isinstance(members, list):
            subs = members
        else:
            subs = []
        for m in subs:
            if isinstance(m, Node) and m.node_name == "TypeImplDecl":
                return m
        return None

    def _process_impls(self, node: Node, slots: dict) -> Node:
        subs = getattr(node, "sub_node", None)
        if subs is None:
            for c in node.iter_children():
                self._process_impls(c, slots)
            return node
        new = []
        for c in subs:
            if c.node_name in ("ImplBinding", "ImplBindingWithInterface"):
                ctx = {
                    "impl_node": c,
                    "type_map": self._type_map,
                    "root_scope": self._root_scope,
                }
                ac = slots.get("auto_connect_ports")
                if ac:
                    ac(c, ctx)
                    self._stats["slots_called"] += 1
                rb = slots.get("replace_impl_binding")
                if rb:
                    result = rb(c, ctx)
                    if result is not None:
                        new.append(result)
                        self._stats["slots_called"] += 1
            else:
                self._process_impls(c, slots)
                new.append(c)
        node.sub_node = new
        return node


    def _build_wrapper(self, td: Node, impl_block: Node) -> Optional[Node]:
        """从 TypeDecl + TypeImplDecl 构建包装模块。"""
        type_name = _node_text(getattr(td, "type_name", None))
        if not type_name:
            return None
        role_name = _first_role_name(self._root_scope, type_name) or "impl"
        wrapper_name = f"{type_name}_{role_name}"
        ports = _get_resolved_ports(self._root_scope, type_name)
        mod = Node("ModuleDecl")
        name_node = Node("Identifier")
        name_node.add_attr("content", wrapper_name)
        mod.add_attr("module_name", name_node)
        type_params = getattr(td, "params", None)
        if type_params:
            plp = _make_param_list(type_params)
            if plp:
                mod.add_attr("params", plp)
        port_items = []
        if ports:
            for p in ports:
                d = _port_decl(p["direction"], p["name"])
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
        body = Node("ModuleBlock")
        body.add_attr("sub_node", [])
        impl_body = getattr(impl_block, "body", None)
        if impl_body:
            if isinstance(impl_body, list):
                body.sub_node = [n for n in impl_body if isinstance(n, Node)]
            elif isinstance(impl_body, Node):
                subs = getattr(impl_body, "sub_node", []) or getattr(impl_body, "items", [])
                body.sub_node = [n for n in subs if isinstance(n, Node)]
        mod.add_attr("body", body)
        mark_extra(wrapper_name, mod)
        return mod


def _node_text(n: Any) -> str:
    if isinstance(n, str):
        return n
    if hasattr(n, "content"):
        return n.content
    if hasattr(n, "iter_children"):
        for c in n.iter_children():
            r = _node_text(c)
            if r:
                return r
    return ""


def _first_role_name(root_scope, type_name: str) -> str:
    sc = root_scope.find_child_scope(type_name, kind="type") if root_scope else None
    if sc is None:
        return ""
    for sym in sc.symbols.values():
        if sym.kind == "role":
            return sym.name
    return ""


def _get_resolved_ports(root_scope, type_name: str) -> list[dict]:
    sc = root_scope.find_child_scope(type_name, kind="type") if root_scope else None
    if sc is None:
        return []
    for sym in sc.symbols.values():
        if sym.kind != "role":
            continue
        resolved = sym.attrs.get("resolved_ports", [])
        if resolved:
            return resolved
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
                name = item.get("name", "") if isinstance(item, dict) else _node_text(item)
                if name:
                    flat.append({"direction": d, "name": name})
        if flat:
            return flat
    return []


def _make_param_list(type_params) -> Optional[Node]:
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
            return _node_text(name)
    return ""


def _port_decl(direction: str, name: str) -> Optional[Node]:
    if not name:
        return None
    cls = "AnsiInputDecl" if direction == "input" else "AnsiOutputDecl"
    decl = Node(cls)
    decl.add_attr("direction", direction)
    lst = Node("DeclaratorList")
    dcl = Node("Declarator")
    nid = Node("Identifier")
    nid.add_attr("content", name)
    dcl.add_attr("name", nid)
    lst.add_attr("items", [dcl])
    decl.add_attr("items", lst)
    return decl
