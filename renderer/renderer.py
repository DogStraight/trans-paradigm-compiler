"""
Renderer — 从 AST + 布局规则直接渲染为格式化文本。

只包含 7 个 DSL 原语（本质硬编码）：
    text / ref / join / group / line / indent / opt

所有语言特定知识（节点名、字段名、关键字等）来自 TOML 布局规则。
AST 规范化层在渲染前将所有 parser 内部构造（keyword/symbol/optional/repeat/sequence/first+rest）
翻译为规范形式，Renderer 无需关心 parser 实现细节。
风格参数（缩进、行宽）来自 _style.toml 配置。
"""

import tomllib
import os
from typing import Any, Optional
from core.define import Node
from .normalizer import normalize_ast


class Renderer:
    """AST → 格式化文本，零语言特定代码"""

    # 默认风格参数（可被 TOML 覆盖）
    _INDENT_STR = "    "
    _MAX_INLINE = 40

    def __init__(self, rules_dir: str):
        self._layouts: dict[str, dict] = {}
        self._children_field = "sub_node"
        self._normalize_config: Optional[dict] = None
        self._load_layouts(rules_dir)
        self._load_style(rules_dir)
        self._load_normalize_config(rules_dir)

    # ---------------------------------------------------------------
    # 布局规则加载
    # ---------------------------------------------------------------
    def _load_layouts(self, rules_dir: str) -> None:
        """从 TOML 规则目录加载所有 layout 定义"""
        from core.define import FileManager

        base = FileManager.get_full_path(rules_dir)
        if not os.path.isdir(base):
            return

        for fname in sorted(os.listdir(base)):
            if not fname.endswith(".toml") or fname.startswith("_"):
                continue
            fpath = os.path.join(base, fname)
            with open(fpath, "rb") as f:
                data = tomllib.load(f)
            for node_type, cfg in data.items():
                if not isinstance(cfg, dict):
                    continue
                layout = {}
                for key in ("layout", "head", "body", "tail", "body_role"):
                    if key in cfg:
                        layout[key] = cfg[key]
                if layout:
                    if node_type in self._layouts:
                        self._layouts[node_type].update(layout)
                    else:
                        self._layouts[node_type] = layout

    def _load_style(self, rules_dir: str) -> None:
        """加载风格配置（来自 _style.toml 或 _formatter.toml）"""
        from core.define import FileManager

        base = FileManager.get_full_path(rules_dir)
        if not os.path.isdir(base):
            return

        for fname in ("_style.toml", "_formatter.toml"):
            fpath = os.path.join(base, fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = tomllib.load(f)
                style = data.get("style", {})
                if "indent" in style:
                    val = style["indent"]
                    if isinstance(val, int):
                        self._INDENT_STR = " " * val
                    else:
                        self._INDENT_STR = val
                if "max_inline" in style:
                    self._MAX_INLINE = style["max_inline"]
                if "children_field" in style:
                    self._children_field = style["children_field"]
                return  # 优先找到哪个用哪个

    def _load_normalize_config(self, rules_dir: str) -> None:
        """加载 AST 规范化配置"""
        from .normalizer import _load_config

        self._normalize_config = _load_config()

    # ---------------------------------------------------------------
    # 入口
    # ---------------------------------------------------------------
    def render(self, node: Node, indent: int = 0) -> str:
        """渲染完整 AST 为格式化文本"""
        node = normalize_ast(node, self._layouts, self._normalize_config)
        if not isinstance(node, Node):
            return str(node) if node else ""
        return self._render_node(node, self._layouts.get(node.name, {}), indent)

    # ---------------------------------------------------------------
    # 节点渲染
    # ---------------------------------------------------------------
    def _render_node(self, node: Node, layout: dict, indent: int) -> str:
        head_expr = layout.get("head") or layout.get("layout")
        body_cfg = layout.get("body")
        tail_expr = layout.get("tail")

        open_line = self._eval(head_expr, node, indent) if head_expr else ""
        body_lines: list[str] = []
        if body_cfg:
            body_lines = self._render_body(node, indent + 1, body_cfg)
        close_line = self._eval(tail_expr, node, indent) if tail_expr else ""

        prefix = self._INDENT_STR * indent
        parts: list[str] = []
        if open_line:
            parts.append(prefix + open_line)
        if body_lines:
            parts.extend(body_lines)
        if close_line:
            parts.append(prefix + close_line)
        if parts:
            return "\n".join(parts)
        # 没有布局规则或布局为空时兜底
        return self._render_fallback(node, indent)

    def _render_fallback(self, node: Node, indent: int) -> str:
        """兜底渲染：无布局规则时的退化处理"""
        return ""

    # ---------------------------------------------------------------
    # DSL 求值器
    # ---------------------------------------------------------------
    def _eval(self, expr: Any, node: Node, indent: int) -> str | None:
        if expr is None:
            return ""

        if isinstance(expr, str):
            return expr

        if not isinstance(expr, dict):
            return str(expr)

        # ---- ref ----
        if "ref" in expr:
            child = getattr(node, expr["ref"], None)
            if child is None:
                return None
            if isinstance(child, Node):
                child_layout = self._layouts.get(child.name, {})
                return self._render_inline(child, child_layout, indent)
            if isinstance(child, list):
                lines = []
                for item in child:
                    if isinstance(item, Node):
                        item_layout = self._layouts.get(item.name, {})
                        r = self._render_inline(item, item_layout, indent)
                    else:
                        r = str(item)
                    if r:
                        lines.append(r)
                return "\n".join(lines)
            return str(child)

        # ---- join ----
        if "join" in expr:
            sep = expr["join"]
            items = self._resolve_items(node, expr.get("items"))
            rendered: list[str] = []
            for item in items:
                if isinstance(item, Node):
                    child_layout = self._layouts.get(item.name, {})
                    r = self._render_inline(item, child_layout, indent)
                else:
                    r = str(item)
                if r:
                    rendered.append(r)
            return sep.join(rendered) if rendered else None

        # ---- group ----
        if "group" in expr:
            parts: list[str] = []
            for e in expr["group"]:
                p = self._eval(e, node, indent)
                if p is None:
                    return None  # ref 引用缺失，整个 group 无意义
                if p != "":
                    parts.append(p)
            if not parts:
                return None

            joined = "".join(parts)
            if len(joined) < self._MAX_INLINE:
                return joined
            inner_indent = self._INDENT_STR * (indent + 1)
            return "\n" + ("\n" + inner_indent).join(parts)

        # ---- line ----
        if "line" in expr:
            parts: list[str] = []
            for e in expr["line"]:
                p = self._eval(e, node, indent)
                if p is not None:
                    parts.append(p)
            return "".join(parts)

        # ---- indent ----
        if "indent" in expr:
            return "\n".join(self._render_body(node, indent + 1))

        # ---- opt ----
        if "opt" in expr:
            inner = expr["opt"]
            # opt 包裹 line 或 ref 时，检查引用是否缺失
            if isinstance(inner, dict):
                refs = []
                if "line" in inner:
                    for e in inner["line"]:
                        if isinstance(e, dict) and "ref" in e:
                            refs.append(e["ref"])
                        if isinstance(e, dict) and "join" in e and "items" in e:
                            refs.append(e["items"])
                if "ref" in inner:
                    refs.append(inner["ref"])
                if "join" in inner and "items" in inner:
                    refs.append(inner["items"])
                for ref in refs:
                    if getattr(node, ref, None) is None:
                        return ""
            result = self._eval(inner, node, indent)
            return result if result else ""

        return ""

    # ---------------------------------------------------------------
    # 渲染变体
    # ---------------------------------------------------------------
    def _render_inline(self, node: Node, layout: dict, indent: int) -> str:
        """内联渲染节点（用于 ref 在 line/group/join 中引用子节点时）"""
        head_expr = layout.get("head") or layout.get("layout")
        body_cfg = layout.get("body")
        tail_expr = layout.get("tail")

        prefix = self._INDENT_STR * indent

        open_line = self._eval(head_expr, node, indent) if head_expr else ""
        body_lines: list[str] = []
        if body_cfg:
            body_lines = self._render_body(node, indent + 1)
        close_line = self._eval(tail_expr, node, indent) if tail_expr else ""

        parts: list[str] = []
        if open_line:
            parts.append(open_line)
        if body_lines:
            parts.extend(body_lines)
        if close_line:
            parts.append(prefix + close_line)
        if parts:
            return "\n".join(parts)
        return self._render_fallback(node, indent)

    # ---------------------------------------------------------------
    # 辅助方法
    # ---------------------------------------------------------------
    def _resolve_items(self, node: Node, items_spec: Optional[str]) -> list:
        """解析 items 引用

        未指定时 → node.{children_field}
        字段名 → 对应属性
        """
        if not items_spec:
            return getattr(node, self._children_field, [])
        attr = getattr(node, items_spec, None)
        if attr is None:
            return []
        if isinstance(attr, list):
            return attr
        return [attr]

    def _render_body(
        self, node: Node, indent: int, body_cfg: Optional[dict] = None
    ) -> list[str]:
        """渲染节点主体：遍历子节点，每个缩进一行

        body_cfg 可指定 source 字段名（如 source = "items"），
        从 node 的该属性获取子节点列表。
        """
        if body_cfg and isinstance(body_cfg, dict):
            source = body_cfg.get("source")
        else:
            source = None

        if source:
            container = getattr(node, source, None)
            if isinstance(container, Node):
                children = getattr(container, self._children_field, [])
            elif isinstance(container, list):
                children = container
            else:
                children = []
        else:
            children = getattr(node, self._children_field, [])

        lines: list[str] = []
        for child in children:
            if not isinstance(child, Node):
                continue
            child_layout = self._layouts.get(child.name, {})
            r = self._render_node(child, child_layout, indent)
            if r:
                lines.append(r)
        return lines
