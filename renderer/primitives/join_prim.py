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
    Doc,
    Empty,
    Text,
    Line as SoftLine,
    Break,
    Concat,
    Nest,
    group,
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

    # 分隔符为 \n → 使用硬换行，不 group
    # 分隔符为空 → 直接拼接，不 group
    is_newline_sep = expr["join"] == "\n"
    no_sep = not expr["join"]

    items = renderer._resolve_items(node, expr.get("items"))
    rendered: List[Doc] = []

    for item in items:
        if isinstance(item, Node):
            merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
            d = renderer._render_inline(item, merged, indent)
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
            if not is_newline_sep and not no_sep:
                result.append(SoftLine())
        if i > 0:
            if is_newline_sep:
                result.append(Break())
            elif no_sep:
                pass  # 直接拼接，不插入任何内容
            else:
                result.append(Text(sep_text))
                result.append(SoftLine())
        result.append(d)

    if suffix:
        result.append(Text(suffix))

    if is_newline_sep or no_sep:
        doc = Concat(result)
    else:
        doc = group(Concat(result))
    if nest_level:
        doc = Nest(nest_level * len(renderer._INDENT_STR), doc)
    return doc
