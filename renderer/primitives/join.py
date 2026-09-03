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
            # 独占行注释（ADR-0013 阶段 B）：_comment 引擎标记（parser
            # collect_line_comments 挂）——列表容器（端口/声明组）内独立行
            # 注释是"项间分隔注释"，不参与 join 分隔符。先收集，组装时
            # 作为独立行插入（前后 Break），见下方注释项处理。
            if getattr(item, "_comment", False):
                merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
                d = renderer._render_inline(item, merged)
                rendered.append((d, [], True))
                continue
            merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
            d = renderer._render_inline(item, merged)
        else:
            d = Text(str(item))
        if not isinstance(d, Empty):
            body, suffixes = _split_trailing_suffix(d)
            rendered.append((body, suffixes, False))

    if not rendered:
        return None

    # 行内分隔（有 sep + SoftLine 可折）：item 尾部 LineSuffix（行尾注释）输出在
    # 分隔符之后、折行点之前（`input clk, // 注释`——注释在逗号后行尾，flat 与
    # broken 均正确）；换行分隔（语句块 join="\n"）保持 item 内（`stmt; // 注释`）。
    inline_sep = not is_newline_sep and not no_sep and not no_soft
    pending_suffix: list[LineSuffix] = []
    result: list[Doc] = []
    if prefix:
        result.append(Text(prefix))

    # 独占行注释（ADR-0013 阶段 B）作"段分隔"：注释项把列表切成多段。
    # 普通项沿用原 join 语义（分隔符在项间输出、行尾注释 LineSuffix 处理）；
    # 注释项打断处：若前项分隔符已输出则 Break 到注释行，注释后下一项为
    # 新段首（无分隔符）。
    after_comment = False
    n_rendered = len(rendered)
    for i, (body, suffixes, is_comment) in enumerate(rendered):
        if is_comment:
            # flush 前项挂起 suffix（前项行尾注释，属前项行尾）
            if pending_suffix:
                result.extend(pending_suffix)
                pending_suffix = []
            if not after_comment:
                if i > 0:
                    # 注释前有普通项：该项行尾补分隔符（端口 `,`——列表未
                    # 结束，分隔符归属前项行尾），随后 Break 到注释行
                    if inline_sep and not no_sep and not no_soft and not is_newline_sep:
                        result.append(Text(sep_text))
                    result.append(Break())
                elif first_soft and inline_sep:
                    result.append(SoftLine())
            result.append(body)
            if i < n_rendered - 1:
                result.append(Break())  # 注释后还有项 → Break；注释在尾则无
            after_comment = True
            continue
        if after_comment:
            # 注释后新段首项：无前置分隔符，直接接正文
            result.append(body)
            if inline_sep:
                pending_suffix = suffixes
            else:
                result.extend(suffixes)
            after_comment = False
            continue
        if i == 0 and first_soft and inline_sep:
            result.append(SoftLine())
        if i > 0:
            if is_newline_sep:
                result.append(Break())
            elif no_sep:
                pass
            elif no_soft:
                result.append(Text(sep_text))
            else:
                result.append(Text(sep_text))
            if inline_sep:
                result.extend(pending_suffix)
                pending_suffix = []
            if inline_sep:
                result.append(SoftLine())
        result.append(body)
        if inline_sep:
            pending_suffix = suffixes
        else:
            result.extend(suffixes)
    if pending_suffix:
        result.extend(pending_suffix)

    if suffix:
        result.append(Text(suffix))

    if is_newline_sep or no_sep or no_soft:
        doc = Concat(result)
    else:
        doc = group(Concat(result))
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc
