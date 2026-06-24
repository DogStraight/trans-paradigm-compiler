"""
join 原语 — 自动宽度感知列表连接

TOML 表示:
    { join = ", ", items = "ports" }
    { join = ",", items = "params", prefix = "(", suffix = ")" }
    { join = ",", items = "items", first_soft = true, nest = 1 }

支持参数:
    join       分隔符文本
    nest       额外缩进层级
    first_soft 第一个元素前加软换行
    prefix     整体前缀
    suffix     整体后缀
"""

from typing import Any, Optional, List
from core.define import Node
from ..doc import (
    Doc, Empty, Text, Line as SoftLine, Concat, Nest, group,
)
from .registry import register


@register("join")
def eval_join(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Optional[Doc]:
    """求值 join 原语"""
    sep_text = expr["join"].rstrip()
    nest_level = expr.get("nest", 0)
    first_soft = expr.get("first_soft", False)
    prefix = expr.get("prefix", "")
    suffix = expr.get("suffix", "")

    items = renderer._resolve_items(node, expr.get("items"))
    rendered: List[Doc] = []

    for item in items:
        if isinstance(item, Node):
            child_layout = dict(renderer._layouts.get(item.node_name, {}))
            item_override = (
                (parent_layout or {})
                .get("override", {})
                .get(item.node_name, {})
            )
            child_layout.update(item_override)
            d = renderer._render_inline(item, child_layout, indent)
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
        doc = Nest(nest_level * len(renderer._INDENT_STR), doc)
    return doc
