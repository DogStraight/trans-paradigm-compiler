"""join 原语 — 列表连接"""

from typing import Any
from core.define import Node
from ..doc import Doc, Empty, Text, Line as SoftLine, Break, Concat, Nest, group
from .registry import register


@register("join")
def eval_join(
    expr: dict, node: Node, parent_layout: dict | None, renderer: Any
) -> Doc | None:
    sep_text = expr["join"].rstrip()
    nest_level = expr.get("nest", 0)
    first_soft = expr.get("first_soft", False)
    prefix = expr.get("prefix", "")
    suffix = expr.get("suffix", "")
    # no_soft: 硬拼接，不插 SoftLine、不 group（用于"必须一行"的列表，
    # 如增强语法 role 端口列表 `master : input clk, input miso, ...;`）。
    # 硬拼接时保留原始分隔符（含尾随空格，如 ", "），避免 rstrip 丢空格。
    no_soft = expr.get("no_soft", False)
    if no_soft:
        sep_text = expr["join"]

    # 分隔符为 \n → 使用硬换行，不 group
    # 分隔符为空 → 直接拼接，不 group
    is_newline_sep = expr["join"] == "\n"
    no_sep = not expr["join"]

    items = renderer._resolve_items(node, expr.get("items"))
    rendered: list[Doc] = []

    for item in items:
        if isinstance(item, Node):
            merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
            d = renderer._render_inline(item, merged)
        else:
            d = Text(str(item))
        if not isinstance(d, Empty):
            rendered.append(d)

    if not rendered:
        return None

    result: list[Doc] = []
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
            elif no_soft:
                result.append(Text(sep_text))  # 硬分隔，无 SoftLine（不折行）
            else:
                result.append(Text(sep_text))
                result.append(SoftLine())
        result.append(d)

    if suffix:
        result.append(Text(suffix))

    if is_newline_sep or no_sep or no_soft:
        doc = Concat(result)
    else:
        doc = group(Concat(result))
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc
