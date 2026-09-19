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


def _leading_slot_docs(slots: dict, renderer: Any) -> list[Doc]:
    """节点**文本前**的注释槽 → Doc 列表（顺序 = 源序，最后一个最贴近节点文本）。

    - `leading`：`Text(comment) + Break()`——注释后换行、注释前不主动 break
      （父级 body 的 Break 提供换行+缩进）。行尾型注释（`a || // c`）由此落地：
      注释紧跟前一片段同行，换行后接本节点（ADR-0014 方向 B）。
    - `leading_own_line`：整块独占成行——块首一个硬换行 + 注释之间单换行 + 块尾
      一个硬换行（逐条各加首尾硬换行会在多条注释间叠空行）。行终止型必须硬换行
      （① 同行后续内容会被行注释吃掉；② 独占成行才能还原源的断行位置）。是否
      行终止由声明驱动 `renderer.comment_ends_line`；块注释逐条 `Text+Break`。
    - `inline`：`Text(comment) + Text(" ")`——同行紧跟节点文本前（`= /* c */ b`）。
      行中注释落在 `inline = true` 规则上时用它（替身节点里没有锚 token，
      `inline_after` 定位不了）。

    抽成函数的原因：布局路径与 **verbatim 直出路径**都要输出前置槽（后者若漏，
    附着在直出节点上的注释连同 marker 承载的原文一起丢）。
    """
    docs: list[Doc] = []
    for c in slots.get("leading") or ():
        docs.append(Text(c))
        docs.append(Break())
    own_line = slots.get("leading_own_line") or ()
    if own_line:
        line_cs = [c for c in own_line if renderer.comment_ends_line(c)]
        if line_cs:
            docs.append(HardBreak())
            for k, c in enumerate(line_cs):
                if k:
                    docs.append(HardBreak())
                docs.append(Text(c.rstrip()))
            docs.append(HardBreak())
        for c in own_line:
            if not renderer.comment_ends_line(c):
                docs.append(Text(c))
                docs.append(Break())
    for c in slots.get("inline") or ():
        docs.append(Text(c))
        docs.append(Text(" "))
    return docs


def _line_suffix_docs(slots: dict) -> tuple[list[Doc], list[Doc]]:
    """注释槽 → (head 行尾 LineSuffix 列表, 节点行尾 LineSuffix 列表)。

    LineSuffix 只在"下一个换行点"前落地：head 布局常以 break 收尾、tail 常有
    尾随空行 break，两处都得插到 break 之前（见 `_insert_before_trailing_break`
    及 `_append_head` / `_append_tail`）——追加在 break 之后会掉到下一行，这是
    块结束符 / 块头行尾注释漂移的根因（`end // c`、`endmodule // c`、
    `module m; // c`，2026-09-13 实测）。
    """
    head_trail = [LineSuffix(" " + c) for c in (slots.get("head_trailing") or [])]
    trail = [LineSuffix(" " + c) for c in (slots.get("trailing") or [])]
    return head_trail, trail


def _render_verbatim(
    verbatim: str,
    slots: dict,
    renderer: Any,
    head_trail_docs: list[Doc],
    trail_docs: list[Doc],
) -> Doc:
    """引擎级 raw 拼接（ADR-0017 决策 4）：整体直出该文本，不走布局、不遍历子节点。

    宏调用视为不可拆原子文本；语言包对宏零知识，本规则是引擎协议。注释槽仍要
    输出（附着注释在节点 span 之外，不丢内容）——**含前置槽**：走布局路径时
    前置槽在后面补出，直出路径必须同样补，否则附着在直出节点上的注释（含 tpc
    marker，其文本承载条件块原文）会静默丢失（2026-09-17 实测：宏调用作 RHS 时
    条件块整块消失）。文本可能含换行（多行构造原样输出）：后续行保留其原有缩进
    （不做重排）。
    """
    pre = _leading_slot_docs(slots, renderer)
    body: Doc = Concat([*pre, Text(verbatim)]) if pre else Text(verbatim)
    return _insert_before_trailing_break(body, [*head_trail_docs, *trail_docs])


def _append_head(
    parts: list[Doc],
    head_expr: Any,
    node: Node,
    layout: dict,
    renderer: Any,
    head_trail_docs: list[Doc],
) -> None:
    """head 段：表达式求值结果插行尾注释后追加（head 常以 break 收尾 → 插 break 前）。"""
    if not head_expr:
        return
    head_doc = eval_expr(head_expr, node, layout, renderer)
    if head_doc is not None:
        parts.append(_insert_before_trailing_break(head_doc, head_trail_docs))


def _append_body(
    parts: list[Doc],
    node: Node,
    body_cfg: Any,
    layout: dict,
    renderer: Any,
) -> None:
    """body 段：每个子节点文档前补 `Break(body_indent)` 并整体 `Nest`。"""
    if not body_cfg:
        return
    body_docs = render_body(node, body_cfg, layout, renderer)
    body_indent = _body_indent(body_cfg, renderer)
    for bd in body_docs:
        parts.append(Break(body_indent))
        parts.append(Nest(body_indent, bd))


def _append_tail(
    parts: list[Doc],
    layout: dict,
    tail_cfg: Any,
    node: Node,
    renderer: Any,
    trail_docs: list[Doc],
) -> None:
    """tail 段：解析 tail 声明（str / dict{text,break} / 表达式）→ Break + 文本
    + 行尾注释 + 尾随空行（tb 个空行含首 Break，故补 tb-1 个）；无 tail 文本时
    仅落行尾注释。
    """
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


def render_node(
    node: Node,
    layout: dict,
    renderer: Any,
) -> Doc:
    """渲染节点为独立块

    不再通过 Prefix 添加第一行缩进；body 的缩进由 body_cfg["indent"]
    控制（true=1 级、false=不缩进、int=N 级，默认 1 级），渲染为
    Break(body_indent) + Nest(body_indent, child_doc)。

    四段顺序：verbatim 直出（命中即返回）→ head → body → tail，最后补节点文本
    前的注释槽（`_leading_slot_docs`，`trailing` 槽已在 tail 段落地故不重复）。

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

    # 注释槽位提前取出：head_trailing 须紧跟 head 输出，trailing 须在 tail 的
    # 尾随空行 break **之前**输出（`_line_suffix_docs` 的 docstring 记了根因）。
    slots = getattr(node, "_comment_slots", None) or {}
    head_trail_docs, trail_docs = _line_suffix_docs(slots)

    verbatim = getattr(node, "_verbatim_text", None)
    if verbatim is not None:
        return _render_verbatim(
            verbatim, slots, renderer, head_trail_docs, trail_docs
        )

    parts: list[Doc] = []
    _append_head(parts, head_expr, node, layout, renderer, head_trail_docs)
    _append_body(parts, node, body_cfg, layout, renderer)
    _append_tail(parts, layout, tail_cfg, node, renderer, trail_docs)
    parts = _leading_slot_docs(slots, renderer) + parts

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
