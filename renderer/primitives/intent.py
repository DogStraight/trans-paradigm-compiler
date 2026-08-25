"""intent 原语 — 布局意图声明（ADR-0006 阶段 4a）

语言包声明"结构 → 布局意图"，引擎推导具体 Doc，消灭手拼 Break/Nest。
意图词表（第一版）：
  - compact  紧凑列表：group(join(sep, first_soft, nest))——可折行列表的
              join 原语别名（消除 `join+first_soft+nest` 手拼四件套）
  - wrap     流式折行：Fill([item, Line, item, ...])——逐元素贪心放置，
              放得下空格、放不下换行（中间态折行）
  - align    绝对列对齐：Align(align, doc)——跨行对齐基准列
  - anchor   行尾锚定：LineSuffix(text)——尾注释锚定

存量布局 TOML 零改写：intent 是新增声明，不改变 layout/body/tail 语义。
Doc: docs/renderer_architecture.md（intent 布局意图声明：compact/wrap/align/anchor）
"""
from typing import Any
from core.define import Node
from ..doc import (
    Doc,
    Empty,
    Text,
    Line,
    Nest,
    Fill,
    Align,
    LineSuffix,
)
from .registry import register


@register("intent")
def eval_intent(expr: dict, node: Node, parent_layout: dict | None,
                renderer: Any) -> Doc | None:
    """求值 intent 原语（布局意图 → Doc 推导）"""
    kind = expr.get("intent")
    if kind == "compact":
        return _intent_compact(expr, node, parent_layout, renderer)
    if kind == "wrap":
        return _intent_wrap(expr, node, parent_layout, renderer)
    if kind == "align":
        return _intent_align(expr, node, parent_layout, renderer)
    if kind == "anchor":
        return _intent_anchor(expr, node, parent_layout, renderer)
    return None


def _intent_compact(expr, node, parent_layout, renderer) -> Doc | None:
    """紧凑列表：group(join(sep, first_soft, nest))。"""
    join_expr = {
        "join": expr.get("sep", ", "),
        "items": expr.get("items"),
        "first_soft": expr.get("first_soft", True),
        "nest": expr.get("nest", 1),
    }
    return renderer._eval(join_expr, node, parent_layout)


def _intent_wrap(expr, node, parent_layout, renderer) -> Doc | None:
    """流式折行：Fill([item, Line, item, Line, ...])。"""
    items = renderer._resolve_items(node, expr.get("items"))
    if not items:
        return None
    parts: list[Doc] = []
    for i, item in enumerate(items):
        if i > 0:
            parts.append(Line())
        if isinstance(item, Node):
            merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
            d = renderer._render_inline(item, merged)
        else:
            d = Text(str(item))
        if d is not None and not isinstance(d, Empty):
            parts.append(d)
    if not parts:
        return None
    doc: Doc = Fill(parts)
    nest_level = expr.get("nest", 0)
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc


def _intent_align(expr, node, parent_layout, renderer) -> Doc | None:
    """绝对列对齐：Align(align, doc)。"""
    inner = expr.get("doc")
    if inner is None:
        return None
    inner_doc = renderer._eval(inner, node, parent_layout)
    if inner_doc is None:
        return None
    return Align(renderer._indent(expr.get("align", 0)), inner_doc)


def _intent_anchor(expr, node, parent_layout, renderer) -> Doc | None:
    """行尾锚定：LineSuffix(text)。"""
    del node, parent_layout, renderer
    return LineSuffix(expr.get("text", ""))
