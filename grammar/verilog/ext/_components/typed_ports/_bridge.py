"""component_bridge.py — 组件变换桥接插件

将组件中注册的 transform 槽位包装为 TransformPlugin，
注册到 AstTransformer 管线。
"""

from typing import Any
from core.define import Node
from analyzer.scope import Scope
from transform.engine import TransformPlugin, register_plugin


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
        self._root_scope: Scope | None = None
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
                    # 通过 build_wrapper 槽位生成包装模块
                    bw = slots.get("build_wrapper")
                    if bw:
                        wrapper = bw(node, ctx)
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

    def _find_type_impl(self, td: Node) -> Node | None:
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
