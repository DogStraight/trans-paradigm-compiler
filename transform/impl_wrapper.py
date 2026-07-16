"""
impl_wrapper.py — Impl 包装模块生成插件

职责：
    遍历 AST，找到 TypeDecl 和 ImplBinding 节点。
    - TypeDecl → 生成包装模块 AST，call mark_extra() 注册为额外文件
        然后从 Root.sub_node 中移除自身
    - ImplBinding → 替换为 ModuleInst（实例化包装模块）

依赖插件顺序：ImplWrapperPlugin 必须在 ConfigDrivenTransform 之前注册。
"""

import hashlib
from typing import Optional
from core.define import Node
from analyzer.scope import Scope
from .pipeline import TransformPlugin, register_plugin, mark_extra


@register_plugin
class ImplWrapperPlugin(TransformPlugin):
    def __init__(self):
        self._stats = {"wrappers": 0, "instances": 0}
        self._root_scope: Scope | None = None

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def process(self, ast: Node, root_scope: Scope) -> Node:
        self._root_scope = root_scope
        self._type_map: dict[str, str] = {}  # var_name -> type_name
        # 第〇阶段：扫描 AST 中所有 TypedPortDecl，建立变量名→类型名映射
        self._scan_typed_ports(ast)
        # 第一阶段：Root.sub_node 中的 TypeDecl → 包装模块 + 删除
        self._collect_wrappers(ast, root_scope)
        # 第二阶段：递归查找 ImplBinding → 替换为 ModuleInst
        self._replace_impls(ast)
        return ast

    def _scan_typed_ports(self, node: Node) -> None:
        """扫描 AST 中的 TypedPortDecl 节点，提取变量名→类型名映射。"""
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

    # ── TypeDecl ──

    def _collect_wrappers(self, root: Node, root_scope: Scope) -> None:
        subs = getattr(root, "sub_node", [])
        remaining = []
        for node in subs:
            if node.node_name == "TypeDecl":
                impl_block = self._find_type_impl(node)
                if impl_block:
                    # 有 impl[role] 块 → 生成包装模块
                    w = self._make_wrapper(node, root_scope, impl_block)
                    if w:
                        self._stats["wrappers"] += 1
                # 无论有无 impl 块，TypeDecl 均从 Root 移除
            else:
                remaining.append(node)
        root.sub_node = remaining

    def _find_type_impl(self, td: Node) -> Optional[Node]:
        """在 TypeDecl 的 body 中查找 TypeImplDecl 子节点。"""
        body = getattr(td, "body", None)
        if body is None:
            return None
        members = getattr(body, "members", None)
        if members is None:
            return None
        # members 可能是 Node 对象（有 sub_node）或普通 list
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

    def _make_wrapper(
        self, td: Node, root_scope: Scope,
        impl_block: Optional[Node] = None,
    ) -> Optional[Node]:
        type_name = _extract_name(td, "type_name")
        if not type_name:
            return None
        # 包装模块名 = type_name + "_" + 第一个 role 名
        role_name = _first_role_name(root_scope, type_name) or "impl"
        wrapper_name = f"{type_name}_{role_name}"
        ports = _get_resolved_ports(root_scope, type_name)
        mod = Node("ModuleDecl")
        name_node = Node("Identifier")
        name_node.add_attr("content", wrapper_name)
        mod.add_attr("module_name", name_node)

        # 传播参数列表：type (parameter MODE = 0, DATA_WIDTH = 8)
        # → module #(parameter MODE = 0, parameter DATA_WIDTH = 8)
        type_params = getattr(td, "params", None)
        if type_params:
            pl_params = _make_param_list(type_params)
            if pl_params:
                mod.add_attr("params", pl_params)

        # 合并端口：接口端口 + impl 块额外端口
        port_items = []
        if ports:
            for p in ports:
                d = _port_decl(p["direction"], p["name"])
                if d:
                    port_items.append(d)
        if impl_block:
            impl_ports = getattr(impl_block, "ports", None)
            if impl_ports:
                ipl = getattr(impl_ports, "items", [])
                for ip in ipl:
                    if ip.node_name not in ("AnsiInputDecl", "AnsiOutputDecl",
                                            "AnsiInoutDecl", "TypedPortDecl"):
                        continue
                    # 避免与接口端口重名
                    pname = _port_name(ip)
                    if pname and not any(
                        _port_name(pi) == pname for pi in port_items
                    ):
                        port_items.append(ip)
        if port_items:
            pl = Node("PortList")
            pl.add_attr("items", port_items)
            mod.add_attr("ports", pl)

        # 合并 body：impl 块实现体（如有）
        body = Node("ModuleBlock")
        body.add_attr("sub_node", [])
        if impl_block:
            impl_body = getattr(impl_block, "body", None)
            if impl_body is None:
                pass
            elif isinstance(impl_body, list):
                body.sub_node = [n for n in impl_body if isinstance(n, Node)]
            elif isinstance(impl_body, Node):
                # 可能是 repeat 节点（@ModuleItem*），也可能是其他包装节点
                subs = (getattr(impl_body, "sub_node", [])
                        or getattr(impl_body, "items", []))
                body.sub_node = [n for n in subs if isinstance(n, Node)]
        mod.add_attr("body", body)
        mark_extra(wrapper_name, mod)
        return mod

    # ── ImplBinding ──

    def _replace_impls(self, node: Node) -> None:
        subs = getattr(node, "sub_node", None)
        if subs is None:
            for c in node.iter_children():
                self._replace_impls(c)
            return
        new = []
        for c in subs:
            if c.node_name in ("ImplBinding", "ImplBindingWithInterface"):
                inst = self._inst_from_impl(c)
                if inst:
                    new.append(inst)
                    self._stats["instances"] += 1
            else:
                self._replace_impls(c)
                new.append(c)
        node.sub_node = new

    def _inst_from_impl(self, impl: Node) -> Optional[Node]:
        """从 ImplBinding 构建 ModuleInst。

        当 interface_ref 存在时，自动从类型信息生成端口连接。
        """
        # ImplBindingWithInterface 使用 type_spec (spi.master) 而非 module_name
        ts = getattr(impl, "type_spec", None)
        if ts is not None:
            type_name = _node_text(getattr(ts, "type_name", None)) or ""
            role_name = _node_text(getattr(ts, "role_name", None)) or ""
            module_name = f"{type_name}_{role_name}" if type_name and role_name else "impl_module"
        else:
            module_name = _extract_name(impl, "module_name") or "impl_module"
        inst_name = _extract_name(impl, "inst_name")
        if not inst_name:
            # 哈希盐：确定性的实例名，相同 impl 产生相同 hash
            iface = getattr(impl, "interface_ref", None)
            salt = module_name
            if iface is not None:
                salt += "_" + _node_text(iface)
            if ts is not None:
                salt += "_" + _node_text(getattr(ts, "type_name", None) or "")
                salt += "_" + _node_text(getattr(ts, "role_name", None) or "")
            h = hashlib.md5(salt.encode()).hexdigest()[:6]
            inst_name = f"u_{module_name}_{h}"
        mi = Node("ModuleInst")
        mi.add_attr("module_name", module_name)
        mi.add_attr("inst_name", inst_name)

        # 接口绑定：自动生成端口连接
        iface = getattr(impl, "interface_ref", None)
        if iface is not None:
            iface_name = _node_text(iface)
            # 从 _type_map 查找接口变量的类型
            type_name = self._type_map.get(iface_name, "")
            all_ports: list[Node] = []

            # 1. 显式端口（来自 impl 的括号列表）
            explicit = getattr(impl, "ports", None)
            explicit_names: set[str] = set()
            if explicit is not None:
                expl_items = getattr(explicit, "items", []) or getattr(explicit, "sub_node", [])
                for ep in expl_items:
                    if isinstance(ep, Node) and ep.node_name == "NamedPortConnect":
                        pn = _node_text(getattr(ep, "port_name", None))
                        if pn:
                            explicit_names.add(pn)
                        all_ports.append(ep)

            # 2. 自动端口（从类型派生，显式同名覆盖）
            if type_name:
                resolved = _get_resolved_ports(self._root_scope, type_name)
                auto_list = self._make_auto_ports(resolved, iface_name) if resolved else None
                if auto_list is not None:
                    auto_items = getattr(auto_list, "items", []) or getattr(auto_list, "sub_node", [])
                    for ap in auto_items:
                        if isinstance(ap, Node) and ap.node_name == "NamedPortConnect":
                            pn = _node_text(getattr(ap, "port_name", None))
                            if pn and pn not in explicit_names:
                                all_ports.append(ap)

            if all_ports:
                npl = Node("NamedPortList")
                npl.add_attr("items", all_ports)
                mi.add_attr("ports", npl)
        return mi

    def _make_auto_ports(
        self, ports: list[dict], iface_name: str
    ) -> Optional[Node]:
        """从解析端口列表自动生成 NamedPortList 节点。

        使用扁平信号名：spi_io_miso（而非层级引用 spi_io.miso）。
        """
        items = []
        for p in ports:
            pname = p.get("name", "")
            if not pname:
                continue
            conn = Node("NamedPortConnect")
            conn.add_attr("port_name", pname)
            # 扁平信号名：iface_name + "_" + port_name
            flat_name = f"{iface_name}_{pname}"
            sig = Node("Identifier")
            sig.add_attr("content", flat_name)
            conn.add_attr("value", sig)
            items.append(conn)
        if not items:
            return None
        npl = Node("NamedPortList")
        npl.add_attr("items", items)
        return npl


# ── helpers ──

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


def _extract_name(parent: Node, attr: str) -> str:
    c = getattr(parent, attr, None)
    return _node_text(c) if c else ""


def _type_of_interface(root_scope: Scope | None, iface_name: str) -> str:
    """从 scope 树查找接口变量的类型名。

    查找路径：模块作用域 → 查找符号（kind=port 或 wire）
    → 从符号 attrs 中提取 type_name。
    """
    if root_scope is None:
        return ""
    # 在模块子作用域中查找符号
    for child in root_scope.children:
        for sym in child.symbols.values():
            if sym.name == iface_name:
                tn = sym.attrs.get("type_name", "")
                if tn:
                    return tn
    return ""


def _first_role_name(root_scope: Scope, type_name: str) -> str:
    """获取类型的第一个 role 名（如 master/slave）。"""
    sc = root_scope.find_child_scope(type_name, kind="type")
    if sc is None:
        return ""
    for sym in sc.symbols.values():
        if sym.kind == "role":
            return sym.name
    return ""


def _get_resolved_ports(root_scope: Scope, type_name: str) -> list[dict]:
    """从 scope 树获取类型的已解析端口列表。"""
    sc = root_scope.find_child_scope(type_name, kind="type")
    if sc is None:
        return []
    for sym in sc.symbols.values():
        if sym.kind != "role":
            continue
        # 优先：resolved_ports（经过 flatten + invert 后的平坦格式）
        resolved = sym.attrs.get("resolved_ports", [])
        if resolved:
            return resolved
        # 次优先：_ref_callbacks 中的 resolved_ports
        cbs = sym.attrs.get("_ref_callbacks", [])
        for cb in cbs:
            rp = cb.get("resolved_ports", [])
            if rp:
                return rp
        # fallback：从原始 ports 提取（node_name + items 格式）
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


def _make_param_list(type_params: Node) -> Optional[Node]:
    """将 TypeParamList (type 声明) 转换为 ParameterList (module 声明)。"""
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


def _port_name(pn: Node) -> str:
    """从端口声明节点提取端口名。"""
    items = getattr(pn, "items", None)
    if items is None:
        return ""
    dcl_list = getattr(items, "items", [])
    for dcl in dcl_list:
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
