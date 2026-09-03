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
            # 节点 sub_node 首部 Comment（ADR-0013 B1.3：容器首元素前独占
            # 注释挂首元素 Comment 子节点）——join 布局内拆为注释段 +
            # 节点主体（注释独立行渲染）。item 主体渲染不引 sub_node
            # （layout 引绑定属性），Comment 不会被 render_node 重复渲染。
            head_cmts = []
            subs = getattr(item, "sub_node", None)
            while subs and getattr(subs[0], "_comment", False):
                head_cmts.append(subs.pop(0))
            for c in head_cmts:
                rendered.append((Text(getattr(c, "value", "")), [], True))
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

    # 容器节点 inline_after 中锚=分隔符的行中注释（ADR-0013 ③补全：
    # `input clk, /* c */ output`——`,` 是 join 分隔符非布局 line 文本元素，
    # line.py 锚消费不到 → join 组装时插到分隔符后）。按收集序（= 分隔符
    # 序）逐 sep 分配，pop 直接作用于节点槽（消费即删，防 pipeline
    # leftover 双份）；注释多于分隔符的残余留给 leftover 兜底。
    sep_anchor = ""
    if sep_text:
        sep_anchor = sep_text.rstrip()
    sep_ia: list = []
    _node_slots = getattr(node, "_comment_slots", None)
    if _node_slots and sep_anchor:
        _ia = _node_slots.get("inline_after") or {}
        if sep_anchor in _ia:
            sep_ia = _ia[sep_anchor]

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
                else:
                    # 列表首项即注释段（容器首元素前独占注释 / B2 头注释）：
                    # 独占行语义——注释前强制 Break（first_soft 的空格会把
                    # 注释贴到父上下文行尾，如 `module m( // head`），
                    # 换行分隔/硬拼场景无 SoftLine 概念则跳过（父已有换行）。
                    if not is_newline_sep and not no_sep and not no_soft:
                        result.append(Break())
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
                if sep_ia:
                    # 分隔符后行中注释（`clk, /* c */ output`）——注释随
                    # 分隔符输出（折行前）；sep 文本已 rstrip（", "→","），
                    # 注释前补空格
                    _t, _ln = sep_ia.pop(0)
                    result.append(Text(" " + _t))
                    result.append(Text(" "))
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

    # 分隔符行中注释槽清理：消费空键即删（未消费残余留给 leftover 兜底）
    if _node_slots is not None and sep_anchor:
        _ia = _node_slots.get("inline_after")
        if _ia and sep_anchor in _ia and not _ia[sep_anchor]:
            del _ia[sep_anchor]
            if not _ia:
                del _node_slots["inline_after"]

    if suffix:
        result.append(Text(suffix))

    if is_newline_sep or no_sep or no_soft:
        doc = Concat(result)
    else:
        doc = group(Concat(result))
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc
