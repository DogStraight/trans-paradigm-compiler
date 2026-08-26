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
    from core.plugin_loader import get_transform_slots

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

        # 第〇阶段：构建 接口实例名 → 类型名 映射（type_map）
        # 从符号表读（typed_port 符号带 capture 的 type_name），不依赖 AST 残留
        # TypedPortDecl——后者会被 ConfigDrivenTransform 的 expand 提前消费，
        # 扫 AST 拿不到（此前 type_map 恒空 → impl 自动连线永不触发的根因）。
        self._scan_typed_ports_scope(root_scope)

        # 第一阶段：Root.sub_node 中的 TypeDecl → 包装模块 + 删除
        ast = self._process_type_decls(ast, slots)

        # 第二阶段：递归替换 ImplBinding
        ast = self._process_impls(ast, slots)

        return ast

    def _scan_typed_ports_scope(self, scope: Scope | None) -> None:
        """递归遍历符号表，收集 typed_port 符号的 (实例名 → 类型名)。"""
        if scope is None:
            return
        for sym in scope.symbols.values():
            if sym.kind != "typed_port":
                continue
            iname = sym.name
            tn = sym.attrs.get("type_name", "")
            if isinstance(tn, str) and tn:
                self._type_map[iname] = tn
        for child in scope.children:
            self._scan_typed_ports_scope(child)

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
        root.add_attr("sub_node", remaining)
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
                        # 注释迁移（注释节点模型步骤 3，P1.5）：impl 绑定 →
                        # ModuleInst 是 1:1 替换，原 impl 节点的注释（行尾
                        # `// 实例化注释` 等）随结构迁到生成的实例节点。
                        from transform.engine import migrate_comments

                        new.append(migrate_comments(c, result))
                        self._stats["slots_called"] += 1
            else:
                self._process_impls(c, slots)
                new.append(c)
        node.sub_node = new
        return node
