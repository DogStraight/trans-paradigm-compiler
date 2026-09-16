"""
node_renderer.py — AST 节点级渲染逻辑

将单个 AST 节点渲染为 Doc IR，处理 head/body/tail 三段式布局。

Doc: renderer/renderer_architecture.md（世界 A 节点级渲染）
"""

from typing import Any, Optional, Sequence
from core.define import Node
from .doc import (
    Doc,
    Empty,
    Text,
    Break,
    HardBreak,
    Line,
    LineBreak,
    Concat,
    Nest,
    Union,
    LineSuffix,
)
from .primitives import eval_expr


def _insert_before_trailing_break(doc: Doc, extra: Sequence[Doc]) -> Doc:
    """把 extra（行尾注释 LineSuffix）插到 doc **末尾换行点之前**。

    分段布局常以 `{ break = true }` / `{ hard_break = true }` / `tail_break`
    收尾（如 `ModuleDecl.renderer.head`、`tail_break = 2`）——LineSuffix 只在
    下一个换行点前落地，追加在 break 之后会掉到下一行。`head` 又常被 group
    包成 `Union`（flat/broken 两支同构、都以 break 收尾），故两支都插。
    注意：含 `HardBreak` 的 head 不再生成 Union（`group()` 直接返回 broken
    形态，见 doc.py）——本函数同时识别 HardBreak 才能在那种形态下插对位置。
    （2026-09-13 修复：块结束符 / 块头行尾注释漂移。）
    """
    if not extra:
        return doc
    if isinstance(doc, Concat) and doc.docs:
        last = doc.docs[-1]
        if isinstance(last, (Line, Break, HardBreak, LineBreak)):
            return Concat([*doc.docs[:-1], *extra, last])
    if isinstance(doc, Union):
        flat = _insert_before_trailing_break(doc.flat, extra)
        broken = _insert_before_trailing_break(doc.broken, extra)
        if flat is not doc.flat or broken is not doc.broken:
            return Union(flat, broken)
    return Concat([doc, *extra])


def _body_indent(body_cfg: dict, renderer: Any) -> int:
    """body_cfg["indent"] → body 缩进格数。

    true = 1 级（indent_spaces 格），false = 0 级（不缩进），int = N 级。
    未声明时默认 1 级（保持既有"body 恒缩进"行为）。
    """
    level = body_cfg.get("indent", 1)
    if isinstance(level, bool):
        level = 1 if level else 0
    return renderer._indent(level)


def render_node(
    node: Node,
    layout: dict,
    renderer: Any,
) -> Doc:
    """渲染节点为独立块

    不再通过 Prefix 添加第一行缩进；body 的缩进由 body_cfg["indent"]
    控制（true=1 级、false=不缩进、int=N 级，默认 1 级），渲染为
    Break(body_indent) + Nest(body_indent, child_doc)。

    Args:
        node: 当前 AST 节点
        layout: 该节点的布局配置
        renderer: Renderer 实例

    Returns:
        Doc IR
    """
    head_expr = layout.get("layout") or layout.get("head")
    body_cfg = layout.get("body")
    tail_cfg = layout.get("tail")

    parts: list[Doc] = []

    # 注释槽位提前取出：head_trailing 须紧跟 head 输出，trailing 须在 tail 的
    # 尾随空行 break **之前**输出。LineSuffix 只在"下一个换行点"前落地，
    # 追加在 break 之后会掉到下一行——这是块结束符/块头行尾注释漂移的根因
    # （`end // c`、`endmodule // c`、`module m; // c`，2026-09-13 实测）。
    slots = getattr(node, "_comment_slots", None) or {}
    head_trail_docs = [
        LineSuffix(" " + c) for c in (slots.get("head_trailing") or [])
    ]
    trail_docs = [LineSuffix(" " + c) for c in (slots.get("trailing") or [])]

    # 引擎级 raw 拼接（ADR-0017 决策 4）：带 `_verbatim_text` 的节点整体直出该
    # 文本——不走布局、不遍历子节点（宏调用视为不可拆原子文本；语言包对宏零知识，
    # 本规则是引擎协议）。注释槽仍要输出（附着注释在节点 span 之外，不丢内容）。
    # 文本可能含换行（多行构造原样输出）：后续行保留其原有缩进（不做重排）。
    verbatim = getattr(node, "_verbatim_text", None)
    if verbatim is not None:
        return _insert_before_trailing_break(
            Text(verbatim), [*head_trail_docs, *trail_docs]
        )

    # --- head ---
    if head_expr:
        head_doc = eval_expr(head_expr, node, layout, renderer)
        if head_doc is not None:
            # head 布局常以 break 收尾（`ModuleDecl.renderer.head`）→ 行尾注释
            # 须插到该 break 之前，否则落到下一行
            parts.append(
                _insert_before_trailing_break(head_doc, head_trail_docs)
            )

    # --- body ---
    if body_cfg:
        body_docs = render_body(node, body_cfg, layout, renderer)
        body_indent = _body_indent(body_cfg, renderer)
        for bd in body_docs:
            parts.append(Break(body_indent))
            parts.append(Nest(body_indent, bd))

    # --- tail ---
    # （trail_docs 已在函数开头取出：须在 tail 的尾随空行 break 之前输出）
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
            tail_doc = eval_expr(tail_cfg, node, layout, renderer)
            tb = layout.get("tail_break", 0)
    if tail_doc is not None:
        tb = layout.get("tail_break", tb)
        parts.append(Break())
        parts.append(tail_doc)
        parts.extend(trail_docs)
        for _ in range(tb - 1):
            parts.append(Break())
    elif trail_docs:
        parts.extend(trail_docs)

    # --- 注释槽位（ADR-0006 注释遍泛化——注释节点模型步骤 1，P1.5）---
    # 节点属性 _comment_slots: {槽位名: [注释文本]}，槽位：
    #   leading  — 节点文本前独立行（`// 前置注释` 在语句上方）
    #   inline   — 节点文本前同行（行中注释：`/* c */ rst_n`，表达式内 token
    #              间隙定位——注释挂"注释后第一 token 所属节点"）
    #   trailing — 节点后行尾锚定（LineSuffix 渲染行尾注释）——已在上面 tail
    #              段按"换行前落地"输出，此处不重复
    slots = getattr(node, "_comment_slots", None)
    if slots:
        lead = slots.get("leading")
        if lead:
            # leading 注释独立行：`Text(comment) + Break()`——注释后换行，
            # 注释前不主动 break（父级 body 的 Break(body_indent) 提供换行+缩进，
            # 避免双换行）；缩进继承外层 Nest。
            lead_docs: list[Doc] = []
            for c in lead:
                lead_docs.append(Text(c))
                lead_docs.append(Break())
            parts = lead_docs + parts
        inline = slots.get("inline")
        if inline:
            # inline 注释同行前置：`Text(comment) + Text(" ")` 插到节点文本
            # 前（head 前）——表达式内 token 间隙（`assign b = /* c */ rst_n`）。
            inline_docs: list[Doc] = []
            for c in inline:
                inline_docs.append(Text(c))
                inline_docs.append(Text(" "))
            parts = inline_docs + parts

    if parts:
        return Concat(parts)
    return Empty()


def render_inline(
    node: Node,
    layout: dict,
    renderer: Any,
) -> Doc:
    """内联渲染节点（用于 ref 在 line/group/join 中引用子节点时）

    render_node 的别名：两者实现刻意一致（都不加 Prefix，body 缩进由
    body_cfg["indent"] 控制）。保持独立入口仅为调用点语义区分。
    """
    return render_node(node, layout, renderer)


def render_body(
    node: Node,
    body_cfg: Optional[dict],
    parent_layout: Optional[dict],
    renderer: Any,
) -> list[Doc]:
    """渲染节点主体：遍历子节点，每个缩进一行

    body_cfg 可指定 source 字段名（如 source = "items"），
    或 items 列表（如 items = ["then_stmt", "else_chain"]），
    从 node 的对应属性获取子节点。
    body_cfg["indent"] 控制缩进级别（true=1 级 / false=不缩进 / int=N 级，
    默认 1 级），实际缩进由 render_node/render_inline 的 body 渲染段执行。
    """
    if body_cfg and isinstance(body_cfg, dict):
        source = body_cfg.get("source")
        items_list = body_cfg.get("items")
    else:
        source = None
        items_list = None

    children_field = renderer._children_field

    if items_list:
        # 具名属性列表：按顺序从 node 提取子节点
        children: list[Node] = []
        for attr_name in items_list:
            val = getattr(node, attr_name, None)
            if val is None:
                continue
            if isinstance(val, Node):
                children.append(val)
            elif isinstance(val, list):
                children.extend(v for v in val if isinstance(v, Node))
    elif source:
        container = node
        # 点路径穿透（如 "body.members" → node.body.members）：
        # 让 body 源可指向嵌套子节点（TypeDecl.body 穿透到 TypeBody.members）
        for part in source.split("."):
            container = getattr(container, part, None)
            if container is None:
                break
        if isinstance(container, Node):
            # 单节点：若为容器（同名 source 属性或 sub_node 非空）取其子节点；
            # 否则把节点本身作为唯一 child——normalize 会把单元素 repeat 展平
            # 为单节点（如 TypeImplDecl.body: repeat[WireDecl] → WireDecl），
            # 此时 source 指向的就是内容本身。
            # 点路径下（source 含 "."）已到达目标节点，直接按容器展开。
            if "." in source:
                sub = getattr(container, children_field, None)
            else:
                sub = getattr(container, source, None)
                if sub is None:
                    sub = getattr(container, children_field, None)
            if sub:
                children = sub if isinstance(sub, list) else [sub]
            else:
                children = [container]
        elif isinstance(container, list):
            children = container
        else:
            children = []
    else:
        children = getattr(node, children_field, [])

    docs: list[Doc] = []
    children_list = [c for c in children if isinstance(c, Node)]
    for i, child in enumerate(children_list):
        merged = renderer._get_merged_layout(parent_layout or {}, child.node_name)
        d = render_node(child, merged, renderer)
        if not isinstance(d, Empty):
            if body_cfg and isinstance(body_cfg, dict):
                sep = body_cfg.get("sep")
                if sep and i < len(children_list) - 1:
                    d = Concat([d, Text(sep)])
            docs.append(d)
    return docs


def resolve_items(
    node: Node,
    items_spec: Optional[str],
    renderer: Any,
) -> list[Any]:
    """解析 items 引用

    未指定时 → node.{children_field}
    字段名 → 对应属性
    """
    if not items_spec:
        return getattr(node, renderer._children_field, [])
    attr = getattr(node, items_spec, None)
    if attr is None:
        return []
    if isinstance(attr, list):
        return attr
    return [attr]
