"""
Renderer — AST + 布局规则驱动的代码生成器

只包含 DSL 原语（text/ref/join/group/line/indent/opt），
所有语言特定知识来自 TOML 布局规则。
AST 规范化层在渲染前将所有 parser 内部构造（keyword/symbol/optional/repeat/sequence/first+rest）
翻译为规范形式，Renderer 无需关心 parser 实现细节。
风格参数（缩进、行宽）来自 _style.toml 配置。
"""

import tomllib
import os
from typing import Any, Optional, List
from core.define import Node
from transform.pre.normalizer import normalize_ast
from .doc import (
    Doc,
    Empty,
    Text,
    Line as SoftLine,
    Break,
    Concat,
    Nest,
    Prefix,
    group,
    layout,
)


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
                layout = cfg.get("renderer")
                if layout and any(
                    k in layout for k in ("layout", "head", "body", "tail")
                ):
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
        from transform.pre.normalizer import _load_config

        self._normalize_config = _load_config()

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
    # 节点渲染
    # ---------------------------------------------------------------
    def _render_node(self, node: Node, layout: dict, indent: int) -> Doc:
        head_expr = layout.get("layout") or layout.get("head")
        body_cfg = layout.get("body")
        tail_cfg = layout.get("tail")

        parts: List[Doc] = []

        # --- head ---
        if head_expr:
            head_doc = self._eval(head_expr, node, indent, layout)
            if head_doc is not None:
                indent_str = self._INDENT_STR * indent
                if indent_str:
                    parts.append(Text(indent_str))
                parts.append(head_doc)

        # --- body ---
        if body_cfg:
            body_docs = self._render_body(node, indent + 1, body_cfg, layout)
            for bd in body_docs:
                parts.append(Break())
                parts.append(bd)

        # --- tail ---
        tail_doc = None
        tb = 0
        if isinstance(tail_cfg, str):
            tail_doc = Text(tail_cfg) if tail_cfg else None
            tb = layout.get("tail_break", 0)
        elif isinstance(tail_cfg, dict):
            if "text" in tail_cfg:
                tail_doc = Text(tail_cfg["text"]) if tail_cfg.get("text") else None
                tb = tail_cfg.get("break", 0)
            else:
                tail_doc = self._eval(tail_cfg, node, indent, layout)
                tb = layout.get("tail_break", 0)
        if tail_doc is not None:
            tb = layout.get("tail_break", tb)
            if isinstance(tb, bool):
                tb = 1 if tb else 0
            indent_str = self._INDENT_STR * indent
            parts.append(Break())
            if indent_str:
                parts.append(Text(indent_str))
            parts.append(tail_doc)
            for _ in range(tb - 1):
                parts.append(Break())

        if parts:
            return Concat(parts)
        return self._render_fallback(node, indent)

    def _render_fallback(self, node: Node, indent: int) -> Doc:
        """兜底渲染：无布局规则时的退化处理"""
        return Empty()

    # ---------------------------------------------------------------
    # DSL 求值器 → Doc
    # ---------------------------------------------------------------
    def _eval(
        self, expr: Any, node: Node, indent: int, parent_layout: dict | None = None
    ) -> Optional[Doc]:
        """将 TOML 布局表达式求值为 Doc"""
        if expr is None:
            return None

        if isinstance(expr, str):
            return Text(expr)

        if not isinstance(expr, dict):
            return Text(str(expr))

        # ---- ref ----
        if "ref" in expr:
            child = getattr(node, expr["ref"], None)
            if child is None:
                return None
            # 合并父规则的 override
            base_layout = (
                self._layouts.get(child.node_name, {})
                if isinstance(child, Node)
                else {}
            )
            override = (
                (parent_layout or {}).get("override", {}).get(child.node_name, {})
                if isinstance(child, Node)
                else {}
            )
            merged = dict(base_layout)
            merged.update(override)
            if isinstance(child, Node):
                return self._render_inline(child, merged, indent)
            if isinstance(child, list):
                docs: List[Doc] = []
                for item in child:
                    if isinstance(item, Node):
                        item_layout = self._layouts.get(item.node_name, {})
                        item_override = (
                            (parent_layout or {})
                            .get("override", {})
                            .get(item.node_name, {})
                        )
                        merged_item = dict(item_layout)
                        merged_item.update(item_override)
                        d = self._render_inline(item, merged_item, indent)
                    else:
                        d = Text(str(item))
                    if not isinstance(d, Empty):
                        docs.append(d)
                return Concat(docs) if docs else None
            return Text(str(child))

        # ---- soft（软换行，Doc IR 的 Line）----
        if "soft" in expr:
            return SoftLine()

        # ---- break（硬换行，Doc IR 的 Line）----
        if "break" in expr:
            return Break()

        # ---- join（自动宽度感知列表，支持 first_soft、prefix、suffix）----
        if "join" in expr:
            sep_text = expr["join"].rstrip()
            nest_level = expr.get("nest", 0)
            first_soft = expr.get("first_soft", False)  # 是否在第一个元素前加软换行
            prefix = expr.get("prefix", "")
            suffix = expr.get("suffix", "")
            items = self._resolve_items(node, expr.get("items"))
            rendered: List[Doc] = []
            for item in items:
                if isinstance(item, Node):
                    child_layout = dict(self._layouts.get(item.node_name, {}))
                    item_override = (
                        (parent_layout or {})
                        .get("override", {})
                        .get(item.node_name, {})
                    )
                    child_layout.update(item_override)
                    d = self._render_inline(item, child_layout, indent)
                else:
                    d = Text(str(item))
                if not isinstance(d, Empty):
                    rendered.append(d)
            if not rendered:
                return None
            result: List[Doc] = []
            if prefix:
                result.append(Text(prefix))
            for i, d in enumerate(rendered):
                if i == 0 and first_soft:
                    result.append(SoftLine())
                if i > 0:
                    result.append(Text(sep_text))
                    result.append(SoftLine())
                result.append(d)
            if suffix:
                result.append(Text(suffix))
            doc: Doc = group(Concat(result))
            if nest_level:
                doc = Nest(nest_level * len(self._INDENT_STR), doc)
            return doc

        # ---- group（Doc IR 的 group）----
        if "group" in expr:
            parts: List[Doc] = []
            for e in expr["group"]:
                d = self._eval(e, node, indent, parent_layout)
                if d is None:
                    return None  # ref 引用缺失，整个 group 无意义
                if not isinstance(d, Empty):
                    parts.append(d)
            if not parts:
                return None
            return group(Concat(parts))

        # ---- line（顺序拼接，支持 nest 和条件 soft）----
        if "line" in expr:
            nest_level = expr.get("nest", 0)
            parts: List[Doc] = []
            had_content = False  # 上一个非 soft 元素是否产生了内容
            for e in expr["line"]:
                if isinstance(e, dict) and e.get("soft"):
                    if had_content:
                        parts.append(SoftLine())
                        had_content = False  # soft 重置，防止连续 soft
                else:
                    d = self._eval(e, node, indent, parent_layout)
                    if d is not None:
                        parts.append(d)
                        had_content = True
            if not parts:
                return None
            doc: Doc = Concat(parts)
            if nest_level:
                doc = Nest(nest_level * len(self._INDENT_STR), doc)
            return doc

        # ---- indent ----
        if "indent" in expr:
            body_docs = self._render_body(node, indent + 1)
            if not body_docs:
                return None
            return Nest(len(self._INDENT_STR), Concat(body_docs))

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
                        return None
            return self._eval(inner, node, indent, parent_layout)

        return None

    # ---------------------------------------------------------------
    # 渲染变体
    # ---------------------------------------------------------------
    def _render_inline(self, node: Node, layout: dict, indent: int) -> Doc:
        """内联渲染节点（用于 ref 在 line/group/join 中引用子节点时）"""
        head_expr = layout.get("layout") or layout.get("head")
        body_cfg = layout.get("body")
        tail_cfg = layout.get("tail")

        parts: List[Doc] = []

        # --- head（内联：不加前缀）---
        if head_expr:
            head_doc = self._eval(head_expr, node, indent, layout)
            if head_doc is not None:
                parts.append(head_doc)

        # --- body ---
        if body_cfg:
            body_docs = self._render_body(node, indent + 1, body_cfg, layout)
            for bd in body_docs:
                parts.append(Break())
                parts.append(bd)

        # --- tail ---
        tail_doc = None
        tb = 0
        if isinstance(tail_cfg, str):
            tail_doc = Text(tail_cfg) if tail_cfg else None
            tb = layout.get("tail_break", 0)
        elif isinstance(tail_cfg, dict):
            if "text" in tail_cfg:
                tail_doc = Text(tail_cfg["text"]) if tail_cfg.get("text") else None
                tb = tail_cfg.get("break", 0)
            else:
                tail_doc = self._eval(tail_cfg, node, indent, layout)
                tb = layout.get("tail_break", 0)
        if tail_doc is not None:
            tb = layout.get("tail_break", tb)
            if isinstance(tb, bool):
                tb = 1 if tb else 0
            indent_str = self._INDENT_STR * indent
            parts.append(Break())
            if indent_str:
                parts.append(Text(indent_str))
            parts.append(tail_doc)
            for _ in range(tb - 1):
                parts.append(Break())

        if parts:
            return Concat(parts)
        return self._render_fallback(node, indent)

    # ---------------------------------------------------------------
    # 辅助方法
    # ---------------------------------------------------------------
    def _resolve_items(self, node: Node, items_spec: Optional[str]) -> List[Any]:
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
        self,
        node: Node,
        indent: int,
        body_cfg: Optional[dict] = None,
        parent_layout: dict | None = None,
    ) -> List[Doc]:
        """渲染节点主体：遍历子节点，每个缩进一行

        body_cfg 可指定 source 字段名（如 source = "items"），
        或 items 列表（如 items = ["then_stmt", "else_chain"]），
        从 node 的对应属性获取子节点。
        """
        if body_cfg and isinstance(body_cfg, dict):
            source = body_cfg.get("source")
            items_list = body_cfg.get("items")
        else:
            source = None
            items_list = None

        if items_list:
            # 具名属性列表：按顺序从 node 提取子节点
            children: List[Node] = []
            for attr_name in items_list:
                val = getattr(node, attr_name, None)
                if val is None:
                    continue
                if isinstance(val, Node):
                    children.append(val)
                elif isinstance(val, list):
                    children.extend(v for v in val if isinstance(v, Node))
        elif source:
            container = getattr(node, source, None)
            if isinstance(container, Node):
                # 优先使用与 source 同名的属性（如 CaseItemList.items），
                # 再回退到 children_field（如 Block.sub_node）
                children = getattr(container, source, None) or getattr(
                    container, self._children_field, []
                )
            elif isinstance(container, list):
                children = container
            else:
                children = []
        else:
            children = getattr(node, self._children_field, [])

        docs: List[Doc] = []
        children_list = [c for c in children if isinstance(c, Node)]
        for i, child in enumerate(children_list):
            child_layout = dict(self._layouts.get(child.node_name, {}))
            child_override = (
                (parent_layout or {}).get("override", {}).get(child.node_name, {})
            )
            child_layout.update(child_override)
            d = self._render_node(child, child_layout, indent)
            if not isinstance(d, Empty):
                if body_cfg and isinstance(body_cfg, dict):
                    sep = body_cfg.get("sep")
                    if sep and i < len(children_list) - 1:
                        d = Concat([d, Text(sep)])
                docs.append(d)
        return docs
