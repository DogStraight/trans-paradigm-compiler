"""slot_runner.py — 通用槽位执行器（引擎插件，语言无关）。

按语言包的**槽位契约声明**（`[[transform.slots]]`，见 `core/component_protocol.md`
§3）驱动组件注册的槽位：

    遍历（walk: top|recursive）→ 触发（on: 节点名）→ 构造 ctx（声明 + 固有通道）
    → 调用 handler → 按 result（extra|none|replace|remove）接回 AST

语言知识全在声明里（触发节点名 / 遍历形态 / ctx 来源 / 结果形态 / ctx 通道的
符号 kind 与 attr）；引擎只按名匹配、按声明机械执行——同 TOML 语法规则与 L1 声明式
checks 的姿态（硬约束：语言知识不进代码）。

固有通道（自动注入，不需声明）：
    root_scope — analyze 产物（scope 树根）
其余通道按 `[transform.ctx_channels]` 声明从 scope 树派生（如
`type_map = { symbol_kind = "typed_port", attr = "type_name" }`）。

Doc: core/component_protocol.md（§3 transform 槽位）
"""

from __future__ import annotations

from typing import Any

from core._protocol import SLOT_CTX_SELF
from core.define import Node

from .engine import TransformPlugin, migrate_comments, register_plugin


@register_plugin(name="slot_runner", requires=["scope"], produces=["slot_transforms"])
class SlotRunnerPlugin(TransformPlugin):
    """按声明驱动组件槽位（遍历 / 触发 / ctx / 接回）。

    契约（ADR-0015 §3）：`requires=["scope"]`（通道从符号表派生）；
    `produces=["slot_transforms"]`（AST 上的槽位变换结果）。**不管时点**——
    时点归管线配置（`[pipeline.units.*]`）。
    """

    def __init__(self, only_slot: str | None = None) -> None:
        """only_slot 非空 → 只跑该槽位（槽位级单元：每槽位一个独立时点）。"""
        self._only_slot = only_slot
        self._stats = {"slots_called": 0}
        self._per_slot: dict[str, int] = {}

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def describe(self) -> dict:
        """自述：本插件跑了哪些槽位、各调用多少次（可视化管道，ADR-0015 §2）。"""
        if not self._per_slot:
            return {}
        return {"slots_called": dict(sorted(self._per_slot.items()))}

    # ── TransformPlugin 接口 ──

    def process(self, ast: Node, root_scope: Any) -> Node:
        from core.plugin_loader import (
            get_transform_ctx_channels,
            get_transform_slot_decls,
            get_transform_slots,
        )

        decls = get_transform_slot_decls()
        handlers = get_transform_slots()
        if self._only_slot is not None:
            only = decls.get(self._only_slot)
            if only is None:
                raise ValueError(f"[transform] 未知槽位: {self._only_slot!r}")
            decls = {self._only_slot: only}
        if not decls or not handlers or root_scope is None:
            return ast
        base_ctx: dict[str, Any] = {"root_scope": root_scope}
        for name, decl in get_transform_ctx_channels().items():
            base_ctx[name] = _build_channel(decl, root_scope)
        for name, decl in decls.items():
            fn = handlers.get(name)
            if fn is None:
                continue  # 加载期已 fail-fast（声明须与注册名一致）；此处防御
            ast = self._run(ast, decl, fn, base_ctx)
        # 物化登记（契约校验，阶段 7）：产出 = 本插件承接的槽位变换
        # （早退路径未承接任何槽位 = 未产出，单元化时会被真产出核验拦下）
        self.note_produced("slot_transforms")
        return ast

    # ── 遍历 / 触发 / 接回 ──

    def _run(self, ast: Node, decl: dict, fn, base_ctx: dict) -> Node:
        if decl["walk"] == "top":
            subs = getattr(ast, "sub_node", None)
            if isinstance(subs, list):
                ast.add_attr(
                    "sub_node", self._process_list(subs, decl, fn, base_ctx)
                )
            return ast
        return self._walk_recursive(ast, decl, fn, base_ctx)

    def _walk_recursive(self, node: Any, decl: dict, fn, base_ctx: dict) -> Any:
        """递归遍历：有 sub_node 列表则处理该层；否则下探 children。"""
        if not isinstance(node, Node):
            return node
        subs = getattr(node, "sub_node", None)
        if isinstance(subs, list):
            node.add_attr("sub_node", self._process_list(subs, decl, fn, base_ctx))
            return node
        for child in node.iter_children():
            self._walk_recursive(child, decl, fn, base_ctx)
        return node

    def _slot_ctx(self, item: Node, decl: dict, base_ctx: dict) -> dict:
        """单节点调用上下文：base_ctx + 声明通道（`SLOT_CTX_SELF` → 节点自身）。"""
        ctx = dict(base_ctx)
        for key, src in decl["ctx"].items():
            ctx[key] = item if src == SLOT_CTX_SELF else _find_node(item, src)
        return ctx

    def _count_slot_call(self, decl: dict) -> None:
        """调用计数（全局计数 + per-slot 计数）。"""
        self._stats["slots_called"] += 1
        name = decl["name"]
        self._per_slot[name] = self._per_slot.get(name, 0) + 1

    def _splice_result(self, item: Node, out: Any, result: str, new: list) -> None:
        """按声明的 result 形态把 handler 产物接回父列表。

        - extra：额外产物由 handler 自己出（`mark_extra`）——返回值**不接回**
          AST（typed_ports build_wrapper 先例：wrapper 是独立文件）
        - replace 且返回了新节点：1:1 替换，注释随迁
        - none 且返回节点：原地变换，接回 handler 返回值
        - 其余（含 replace 但未换节点）：保留原节点
        """
        if result == "extra":
            new.append(item)
        elif result == "replace" and isinstance(out, Node) and out is not item:
            new.append(migrate_comments(item, out))
        elif result == "none" and isinstance(out, Node):
            new.append(out)
        else:
            new.append(item)

    def _process_list(
        self, items: list, decl: dict, fn, base_ctx: dict
    ) -> list:
        """逐项跑 slot handler：命中 `on` 规则 → 调用并接回；否则按声明的
        walk 模式下探（`recursive`）。`remove` 形态直接不接回（从父列表移除）。"""
        on = set(decl["on"])
        result = decl["result"]
        recursive = decl["walk"] == "recursive"
        new: list = []
        for item in items:
            if isinstance(item, Node) and item.node_name in on:
                out = fn(item, self._slot_ctx(item, decl, base_ctx))
                self._count_slot_call(decl)
                if result == "remove":
                    continue  # 不接回（从父列表移除）
                self._splice_result(item, out, result, new)
                continue
            if recursive:
                self._walk_recursive(item, decl, fn, base_ctx)
            new.append(item)
        return new


def _build_channel(decl: dict, root_scope: Any) -> dict[str, str]:
    """按声明从 scope 树派生一个 ctx 通道：{符号名: attrs[attr]}。"""
    table: dict[str, str] = {}
    kind = decl["symbol_kind"]
    attr = decl["attr"]

    def _walk(scope: Any) -> None:
        for sym in getattr(scope, "symbols", {}).values():
            if getattr(sym, "kind", "") != kind:
                continue
            val = getattr(sym, "attrs", {}).get(attr, "")
            if isinstance(val, str) and val:
                table[sym.name] = val
        for child in getattr(scope, "children", []) or []:
            _walk(child)

    _walk(root_scope)
    return table


def _find_node(node: Any, node_name: str) -> Any:
    """子树内首个 `node_name` 节点（先序 DFS）；未找到 → None。"""
    if not isinstance(node, Node):
        return None
    for child in node.iter_children():
        if getattr(child, "node_name", "") == node_name:
            return child
        found = _find_node(child, node_name)
        if found is not None:
            return found
    return None
