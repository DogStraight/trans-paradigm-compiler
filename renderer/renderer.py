"""Renderer — AST + layout-rule-driven code generator.

Contains only DSL primitives (text/ref/join/group/line/indent/opt).
All language-specific knowledge comes from TOML layout rules.
The AST normalizer converts parser-internal constructs
(keyword/symbol/optional/repeat/sequence/first+rest)
before rendering.

Doc: renderer/renderer_architecture.md（世界 A 入口）
"""

from typing import Any
from core.define import CHILDREN_FIELD, Node
from transform.normalizer import normalize_ast
from .doc import Doc, layout
from .primitives import eval_expr
from .node_renderer import render_node, render_inline, render_body, resolve_items
from .loader import load_layouts, load_style


class Renderer:
    """AST → 格式化文本，零语言特定代码"""

    # 默认风格参数（可被 TOML 覆盖）
    _INDENT_STR = "    "
    _MAX_INLINE = 40

    def __init__(self, rules_dir: str, line_comment_starts: tuple[str, ...] = ()):
        self._layouts: dict[str, dict] = {}
        self._children_field = CHILDREN_FIELD
        # 行终止型注释起点（声明驱动：语言包 `[comment] pairs` 的 kind，
        # 由调用方从 lexer 取——见 Lexer.line_terminating_comment_starts）
        self._line_comment_starts = line_comment_starts
        load_layouts(rules_dir, self._layouts)
        self._apply_style(rules_dir)
        # 布局合并缓存 {(parent_type, child_type): merged_layout}
        self._merged_layout_cache: dict[tuple[str, str], dict] = {}

    def comment_ends_line(self, text: str) -> bool:
        """注释文本是否属"到行边界终止"型（声明驱动，非硬编码标点）。

        是 → 其后不得再接同行元素：回读时这些元素会被并入注释文本
        （`output x // c);` → 端口表未闭合）。列表末项/项间据此补硬换行。
        """
        stripped = text.lstrip()
        return any(stripped.startswith(s) for s in self._line_comment_starts)

    def _get_merged_layout(self, parent_layout: dict, child_node_name: str) -> dict:
        """获取子节点的合并后布局（base_layout + override），带缓存"""
        parent_type = None
        for ptype, pl in self._layouts.items():
            if pl is parent_layout:
                parent_type = ptype
                break
        if parent_type:
            key = (parent_type, child_node_name)
            cached = self._merged_layout_cache.get(key)
            if cached is not None:
                return cached
        key = None  # 无父类型时不缓存
        base = dict(self._layouts.get(child_node_name, {}))
        override = (parent_layout or {}).get("override", {}).get(child_node_name, {})
        base.update(override)
        if parent_type and key is not None:
            self._merged_layout_cache[key] = base
        return base

    def _apply_style(self, rules_dir: str) -> None:
        """从 TOML 加载风格参数到实例属性"""
        style = load_style(rules_dir)
        self._INDENT_STR = style["indent_str"]
        self._MAX_INLINE = style["max_inline"]

    # ── 缩进统一模型（ADR-0006 阶段 1）──
    # 缩进只有两个来源，均以 _INDENT_STR 为"单位"换算：
    #   - body_cfg["indent"]（body 段，node_renderer._body_indent 调用）
    #   - expr {indent: N}（line/soft/break 原语）
    # _indent(level) 是唯一换算点："N 级 × 单位格数"。
    def _indent(self, level: int) -> int:
        """缩进级别 → 空格数（唯一换算点）。"""
        return level * len(self._INDENT_STR)

    # ── 入口 ──
    def render(self, node: Node) -> str:
        """渲染完整 AST 为格式化文本

        若 AST 根节点携带 _indent_unit（auto 缩进模式 lexer 锁定的单位，
        见 lexer/main_lexer.py），渲染期间按该单位换算缩进——渲染输出与
        源文件缩进风格一致（块标量逐字内容相对列对齐不被破坏）。
        """
        node = normalize_ast(node, self._layouts)
        if not isinstance(node, Node):
            return str(node) if node else ""
        unit = getattr(node, "_indent_unit", None)
        saved = self._INDENT_STR
        if isinstance(unit, int) and unit > 0:
            self._INDENT_STR = " " * unit
        try:
            doc = self._render_node(node, self._layouts.get(node.node_name, {}))
            return layout(doc, self._MAX_INLINE)
        finally:
            self._INDENT_STR = saved

    # ── 节点渲染（委托到 node_renderer）──
    def _render_node(self, node: Node, layout_cfg: dict) -> Doc:
        return render_node(node, layout_cfg, self)

    def _render_inline(self, node: Node, layout_cfg: dict) -> Doc:
        return render_inline(node, layout_cfg, self)

    def _render_body(
        self,
        node: Node,
        body_cfg: dict | None = None,
        parent_layout: dict | None = None,
    ) -> list[Doc]:
        return render_body(node, body_cfg, parent_layout, self)

    def _resolve_items(self, node: Node, items_spec: str | None) -> list[Any]:
        return resolve_items(node, items_spec, self)

    # ── DSL 求值（委托到 primitives）──
    def _eval(
        self, expr: Any, node: Node, parent_layout: dict | None = None
    ) -> Doc | None:
        return eval_expr(expr, node, parent_layout, self)
