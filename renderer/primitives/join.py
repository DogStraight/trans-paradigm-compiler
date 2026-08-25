"""join 原语 — 列表连接

Doc: docs/renderer_architecture.md（join 列表拼接原语）
"""

from typing import Any
from core.define import Node
from ..doc import Doc, Empty, Text, Line as SoftLine, Break, Concat, Nest, LineSuffix, group
from .registry import register


def _split_trailing_suffix(doc: Doc) -> tuple[Doc, list[LineSuffix]]:
    """递归拆出 doc 尾部（后序遍历最后叶子）的 LineSuffix 链。

    列表项的行尾注释（`input clk, // 注释`——注释在分隔符后）挂在本项节点，
    渲染为节点 doc 尾部 LineSuffix；inline 展开嵌套（AnsiPortDecl → decl）
    会让 LineSuffix 落在嵌套 Concat 尾——递归到最后叶子提取。
    """
    if isinstance(doc, LineSuffix):
        return Empty(), [doc]
    if isinstance(doc, Concat):
        docs = list(doc.docs)
        if docs:
            last_body, last_suf = _split_trailing_suffix(docs[-1])
            if last_suf:
                head = docs[:-1]
                if not isinstance(last_body, Empty):
                    head = head + [last_body]
                return (Concat(head) if head else Empty()), last_suf
    return doc, []


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
    rendered: list[tuple[Doc, list[LineSuffix]]] = []

    for item in items:
        if isinstance(item, Node):
            merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
            d = renderer._render_inline(item, merged)
        else:
            d = Text(str(item))
        if not isinstance(d, Empty):
            body, suffixes = _split_trailing_suffix(d)
            rendered.append((body, suffixes))

    if not rendered:
        return None

    result: list[Doc] = []
    if prefix:
        result.append(Text(prefix))

    # 行内分隔（有 sep + SoftLine 可折）：item 尾部 LineSuffix（行尾注释）输出在
    # 分隔符之后、折行点之前（`input clk, // 注释`——注释在逗号后行尾，flat 与
    # broken 均正确）；换行分隔（语句块 join="\n"）保持 item 内（`stmt; // 注释`）。
    inline_sep = not is_newline_sep and not no_sep and not no_soft
    pending_suffix: list[LineSuffix] = []
    for i, (body, suffixes) in enumerate(rendered):
        if i == 0 and first_soft and inline_sep:
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
            if inline_sep:
                # 分隔符后、折行点前输出上一项注释（sep_text 已 rstrip 尾空格，
                # LineSuffix 自带前导空格 → `, // 注释`）；broken 时注释在行尾
                result.extend(pending_suffix)
                pending_suffix = []
            if inline_sep:
                result.append(SoftLine())
        result.append(body)
        if inline_sep:
            pending_suffix = suffixes  # 推迟到下一个分隔符后（或列表尾）
        else:
            result.extend(suffixes)  # 换行/硬拼接：注释保持 item 内（行尾）
    if pending_suffix:
        result.extend(pending_suffix)  # 最后一项注释：列表尾（无后续分隔符）

    if suffix:
        result.append(Text(suffix))

    if is_newline_sep or no_sep or no_soft:
        doc = Concat(result)
    else:
        doc = group(Concat(result))
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc
