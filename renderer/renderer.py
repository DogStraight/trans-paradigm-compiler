"""
Renderer — AST + 布局规则驱动的代码生成器

只包含 DSL 原语（text/ref/join/group/line/indent/opt），
所有语言特定知识来自 TOML 布局规则。
AST 规范化层在渲染前将所有 parser 内部构造（keyword/symbol/optional/repeat/sequence/first+rest）
翻译为规范形式，Renderer 无需关心 parser 实现细节。
风格参数（缩进、行宽）来自 _style.toml 配置。

关键设计：
- renderer.py: 轻量的 orchestrator，暴露公共 API
- primitives/: 每个 DSL 原语一个文件，共 8 个原语
- node_renderer.py: 节点级渲染（_render_node / _render_inline / _render_body）
- loader.py: TOML 加载逻辑
- doc.py: Doc IR 类型 + layout 算法
"""

from typing import Any, Optional, List
from core.define import Node
from transform.pre.normalizer import normalize_ast
from .doc import Doc, layout
from .primitives import eval_expr
from .node_renderer import render_node, render_inline, render_body, resolve_items
from .loader import load_layouts, load_style, load_normalize_config


class Renderer:
    """AST → 格式化文本，零语言特定代码"""

    # 默认风格参数（可被 TOML 覆盖）
    _INDENT_STR = "    "
    _MAX_INLINE = 40

    def __init__(self, rules_dir: str):
        self._layouts: dict[str, dict] = {}
        self._children_field = "sub_node"
        self._normalize_config: Optional[dict] = None
        load_layouts(rules_dir, self._layouts)
        self._apply_style(rules_dir)
        self._normalize_config = load_normalize_config(rules_dir)
        # 布局合并缓存 {(parent_type, child_type): merged_layout}
        self._merged_layout_cache: dict[tuple[str, str], dict] = {}

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
        self._children_field = style["children_field"]

    # ---------------------------------------------------------------
    # 入口
    # ---------------------------------------------------------------
    def render(self, node: Node, indent: int = 0) -> str:
        """渲染完整 AST 为格式化文本"""
        node = normalize_ast(node, self._layouts, self._normalize_config)
        if not isinstance(node, Node):
            return str(node) if node else ""
        doc = self._render_node(node, self._layouts.get(node.node_name, {}), indent)
        return layout(doc, self._MAX_INLINE)

    # ---------------------------------------------------------------
    # 节点渲染（委托到 node_renderer）
    # ---------------------------------------------------------------
    def _render_node(self, node: Node, layout_cfg: dict, indent: int) -> Doc:
        return render_node(node, layout_cfg, indent, self)

    def _render_inline(self, node: Node, layout_cfg: dict, indent: int) -> Doc:
        return render_inline(node, layout_cfg, indent, self)

    def _render_body(
        self,
        node: Node,
        indent: int,
        body_cfg: Optional[dict] = None,
        parent_layout: Optional[dict] = None,
    ) -> List[Doc]:
        return render_body(node, indent, body_cfg, parent_layout, self)

    def _resolve_items(self, node: Node, items_spec: Optional[str]) -> List[Any]:
        return resolve_items(node, items_spec, self)

    # ---------------------------------------------------------------
    # DSL 求值（委托到 primitives）
    # ---------------------------------------------------------------
    def _eval(
        self, expr: Any, node: Node, indent: int, parent_layout: Optional[dict] = None
    ) -> Optional[Doc]:
        return eval_expr(expr, node, indent, parent_layout, self)
