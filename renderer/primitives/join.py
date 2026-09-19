"""join 原语 — 列表连接

Doc: renderer/renderer_architecture.md（join 列表拼接原语）
"""

from typing import Any
from dataclasses import dataclass, field
from core.define import Node
from ..doc import Doc, Empty, Text, Line as SoftLine, Break, HardBreak, Concat, Nest, LineSuffix, group
from .registry import register

# 分段节点（有 head/body/tail 段）的布局键——其在列表项中的首部注释归 body 段
_SEGMENT_KEYS = ("head", "body", "tail")


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


@dataclass(frozen=True)
class _JoinCfg:
    """join 原语的配置面（读一次，渲染/组装/包裹三阶段共用）。"""

    sep_text: str        # 项间分隔文本（no_soft 时不 rstrip，保留尾随空格）
    sep_anchor: str      # 行中注释锚（= sep_text.rstrip()）
    nest_level: int
    first_soft: bool
    prefix: str
    suffix: str
    no_soft: bool
    is_newline_sep: bool
    no_sep: bool
    inline_sep: bool     # 行内分隔（有 sep + SoftLine 可折）

    @classmethod
    def from_expr(cls, expr: dict) -> "_JoinCfg":
        """从原语配置读各项；`inline_sep` 与 `sep_anchor` 是派生态，一并算好。"""
        sep_text = expr["join"].rstrip()
        # no_soft: 硬拼接，不插 SoftLine、不 group（用于"必须一行"的列表，
        # 如增强语法 role 端口列表 `master : input clk, input miso, ...;`）。
        # 硬拼接时保留原始分隔符（含尾随空格，如 ", "），避免 rstrip 丢空格。
        no_soft = expr.get("no_soft", False)
        if no_soft:
            sep_text = expr["join"]
        # 分隔符为 \n → 使用硬换行，不 group；为空 → 直接拼接，不 group
        is_newline_sep = expr["join"] == "\n"
        no_sep = not expr["join"]
        return cls(
            sep_text=sep_text,
            sep_anchor=sep_text.rstrip() if sep_text else "",
            nest_level=expr.get("nest", 0),
            first_soft=expr.get("first_soft", False),
            prefix=expr.get("prefix", ""),
            suffix=expr.get("suffix", ""),
            no_soft=no_soft,
            is_newline_sep=is_newline_sep,
            no_sep=no_sep,
            inline_sep=not is_newline_sep and not no_sep and not no_soft,
        )


def _split_head_comments(
    item: Node, renderer: Any
) -> list[tuple[Doc, list[LineSuffix], bool]]:
    """节点 sub_node 首部 Comment 子节点 → 独立行注释条目（并从 sub_node 摘除）。

    ADR-0013 B1.3：容器首元素前独占注释挂首元素 Comment 子节点——join 布局内
    拆为注释段 + 节点主体（注释独立行渲染）。item 主体渲染不引 sub_node
    （layout 引绑定属性），Comment 不会被 render_node 重复渲染。

    ⚠ 只对**非分段节点**（无 head/body/tail 的列表项，如 Declarator/端口项）拆：
    **分段节点**（ModuleDecl 等有 head/body/tail）的 sub_node 就是它的 body，
    首部 Comment 属 body 首注释，归 render_node 的 body 段渲染——若在此拆出，
    注释会渲染到节点 head 之前（`// 注释` 漂到 `module` 声明前；回归
    `tests/languages/verilog/test_comment_body_head.py`）。
    """
    item_layout = renderer._layouts.get(item.node_name, {})
    if any(k in item_layout for k in _SEGMENT_KEYS):
        return []
    head_cmts: list[Node] = []
    subs = getattr(item, "sub_node", None)
    while subs and getattr(subs[0], "_comment", False):
        head_cmts.append(subs.pop(0))
    return [(Text(getattr(c, "value", "")), [], True) for c in head_cmts]


def _render_join_item(
    item: Any, parent_layout: dict | None, renderer: Any
) -> list[tuple[Doc, list[LineSuffix], bool]]:
    """单项渲染 → 0..n 条 (项正文, 尾部 LineSuffix 链, 是否独占行注释)。

    三类项：独占行注释项（`_comment` 标记，段分隔用）→ 1 条注释条目；
    节点项（可能带首部 Comment 子节点 → 注释条目 + 主体）；非节点项（直接
    文本化）。渲染为 Empty 的节点不产出条目。
    """
    if not isinstance(item, Node):
        return [(Text(str(item)), [], False)]

    # 独占行注释（ADR-0013 阶段 B）：_comment 引擎标记（parser
    # collect_line_comments 挂）——列表容器（端口/声明组）内独立行
    # 注释是"项间分隔注释"，不参与 join 分隔符。作为独立行插入
    # （前后 Break），见 `_asm_comment_item`。
    if getattr(item, "_comment", False):
        merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
        d = renderer._render_inline(item, merged)
        return [(d, [], True)]

    entries = _split_head_comments(item, renderer)
    merged = renderer._get_merged_layout(parent_layout or {}, item.node_name)
    d = renderer._render_inline(item, merged)
    if not isinstance(d, Empty):
        body, suffixes = _split_trailing_suffix(d)
        entries.append((body, suffixes, False))
    return entries


def _render_join_items(
    items: list, parent_layout: dict | None, renderer: Any
) -> list[tuple[Doc, list[LineSuffix], bool]]:
    """渲染每个列表项 → [(项正文, 尾部 LineSuffix 链, 是否独占行注释)]。"""
    rendered: list[tuple[Doc, list[LineSuffix], bool]] = []
    for item in items:
        rendered.extend(_render_join_item(item, parent_layout, renderer))
    return rendered


def _take_sep_inline_after(node: Node, sep_anchor: str) -> list:
    """取容器节点 inline_after 里锚=分隔符的行中注释槽（**返回原槽列表**）。

    容器节点 inline_after 中锚=分隔符的行中注释（ADR-0013 ③补全：
    `input clk, /* c */ output`——`,` 是 join 分隔符非布局 line 文本元素，
    line.py 锚消费不到 → join 组装时插到分隔符后）。按收集序（= 分隔符序）
    逐 sep 分配，`pop` 直接作用于节点槽（消费即删——B1.4 已删 leftover 回插
    通道，残余不再兜底）。
    """
    if not sep_anchor:
        return []
    slots = getattr(node, "_comment_slots", None)
    if not slots:
        return []
    inline_after = slots.get("inline_after") or {}
    return inline_after.get(sep_anchor) or []


def _cleanup_sep_slot(node: Node, sep_anchor: str) -> None:
    """分隔符行中注释槽清理：消费空键即删（B1.4 已删 leftover 回插通道）。"""
    if not sep_anchor:
        return
    slots = getattr(node, "_comment_slots", None)
    if slots is None:
        return
    inline_after = slots.get("inline_after")
    if inline_after and sep_anchor in inline_after and not inline_after[sep_anchor]:
        del inline_after[sep_anchor]
        if not inline_after:
            del slots["inline_after"]


@dataclass
class _AssembleState:
    """join 组装状态（跨项复用）。

    `sep_ia` 是分隔符行中注释槽的**原列表引用**（`pop` 直接作用于节点槽，
    消费即删——见 `_take_sep_inline_after`）。
    """

    result: list[Doc] = field(default_factory=list)
    pending_suffix: list[LineSuffix] = field(default_factory=list)
    sep_ia: list = field(default_factory=list)
    after_comment: bool = False  # 上一项是独占行注释 → 本项是段首（无前置分隔符）


def _asm_comment_item(
    state: _AssembleState, body: Doc, i: int, n_rendered: int, cfg: _JoinCfg
) -> None:
    """独占行注释项（ADR-0013 阶段 B）：把列表切成多段——注释前 Break、注释后
    Break（注释在尾则无），段首无分隔符。

    注释前分两情形：
    - 前面有普通项（i > 0）：该项行尾补分隔符（端口 `,`——列表未结束，分隔符
      归属前项行尾），随后 Break 到注释行；
    - 列表首项即注释段（容器首元素前独占注释 / B2 头注释）：独占行语义——注释前
      强制 Break（first_soft 的空格会把注释贴到父上下文行尾，如
      `module m( // head`），换行分隔/硬拼场景无 SoftLine 概念则跳过（父已有换行）。
    """
    # flush 前项挂起 suffix（前项行尾注释，属前项行尾）
    if state.pending_suffix:
        state.result.extend(state.pending_suffix)
        state.pending_suffix = []
    if not state.after_comment:
        if i > 0:
            if cfg.inline_sep:
                state.result.append(Text(cfg.sep_text))
            state.result.append(Break())
        elif not cfg.is_newline_sep and not cfg.no_sep and not cfg.no_soft:
            state.result.append(Break())
    state.result.append(body)
    if i < n_rendered - 1:
        state.result.append(Break())  # 注释后还有项 → Break；注释在尾则无
    state.after_comment = True


def _asm_separator(
    state: _AssembleState, i: int, cfg: _JoinCfg, renderer: Any
) -> None:
    """分隔符段：段首 SoftLine（first_soft）+ 项间分隔符 + 行尾注释时序。

    - 分隔符形态：换行分隔 → Break；`no_sep` → 无分隔；`no_soft` → 硬拼文本；
      否则 sep 文本 + 分隔符后行中注释（注释随分隔符输出、在折行前）。
    - 行内分隔下挂起的行尾注释在此落地：到行边界终止型（语言包声明的
      `renderer.comment_ends_line`）须换行且**强制组断开**——否则扁平化会把
      分隔符折成空格、注释吞掉后续项（`input a, // c output b`）。
    """
    if i == 0 and cfg.first_soft and cfg.inline_sep:
        state.result.append(SoftLine())
    if i == 0:
        return
    if cfg.is_newline_sep:
        state.result.append(Break())
    elif cfg.no_sep:
        pass
    elif cfg.no_soft:
        state.result.append(Text(cfg.sep_text))
    else:
        state.result.append(Text(cfg.sep_text))
        if state.sep_ia:
            # 分隔符后行中注释（`clk, /* c */ output`）——注释随分隔符输出
            # （折行前）；sep 文本已 rstrip（", "→","），注释前补空格
            _t, _ = state.sep_ia.pop(0)
            state.result.append(Text(" " + _t))
            state.result.append(Text(" "))
    if cfg.inline_sep:
        ends_line = any(
            renderer.comment_ends_line(s.text) for s in state.pending_suffix
        )
        state.result.extend(state.pending_suffix)
        state.pending_suffix = []
        state.result.append(HardBreak() if ends_line else SoftLine())


def _asm_append_item(
    state: _AssembleState, body: Doc, suffixes: list[LineSuffix], cfg: _JoinCfg
) -> None:
    """项正文落地 + 行尾注释时序：行内分隔下挂起到分隔符之后，否则直接输出在项内。"""
    state.result.append(body)
    if cfg.inline_sep:
        state.pending_suffix = suffixes
    else:
        state.result.extend(suffixes)


def _asm_flush_tail(state: _AssembleState, renderer: Any) -> None:
    """末项挂起行尾注释落地。

    属"到行边界终止"型（行注释）时，行必须在此结束且**所在组必须断开**
    （HardBreak 向上传播）：列表后面若还有同行布局元素（模块端口关闭 `)` `;`），
    注释会把它们吃进注释文本（`output [3:0] DEBUG // ... :));` → 端口表未闭合，
    2026-09-17）。哪种注释属该型由语言包声明（renderer.comment_ends_line），
    引擎不硬编码标点；块注释保持同行（`input clk, /* c */ output`）。
    """
    if not state.pending_suffix:
        return
    state.result.extend(state.pending_suffix)
    if any(renderer.comment_ends_line(s.text) for s in state.pending_suffix):
        state.result.append(HardBreak())


def _assemble_join(
    rendered: list[tuple[Doc, list[LineSuffix], bool]],
    cfg: _JoinCfg,
    sep_ia: list,
    renderer: Any,
) -> list[Doc]:
    """按 join 语义组装 Doc 序列（含独占行注释分段、分隔符与行尾注释时序）。

    - 项尾部 LineSuffix（行尾注释）在**行内分隔**下输出在分隔符之后、折行点
      之前（`input clk, // 注释`——flat 与 broken 均正确）；换行分隔
      （`join="\\n"`）保持项内（`stmt; // 注释`）。
    - 独占行注释项把列表切成多段（`_asm_comment_item`）。
    - 末项行尾注释的硬断行收口见 `_asm_flush_tail`。
    """
    state = _AssembleState(sep_ia=sep_ia)
    if cfg.prefix:
        state.result.append(Text(cfg.prefix))

    n_rendered = len(rendered)
    for i, (body, suffixes, is_comment) in enumerate(rendered):
        if is_comment:
            _asm_comment_item(state, body, i, n_rendered, cfg)
            continue
        if state.after_comment:
            # 注释后新段首项：无前置分隔符，直接接正文
            state.after_comment = False
            _asm_append_item(state, body, suffixes, cfg)
            continue
        _asm_separator(state, i, cfg, renderer)
        _asm_append_item(state, body, suffixes, cfg)

    _asm_flush_tail(state, renderer)
    return state.result

@register("join")
def eval_join(
    expr: dict, node: Node, parent_layout: dict | None, renderer: Any
) -> Doc | None:
    """join 原语：列表连接（分隔符 / 折行 / 行尾注释 / 段分隔注释）。

    四阶段：读配置（`_JoinCfg.from_expr`）→ 渲染各项
    （`_render_join_items`）→ 组装（`_assemble_join`，含分隔符注释槽）→
    包裹（group 与否 + nest）。
      - 分隔符为 `\\n` / 空 / `no_soft`：不 group（硬拼或项内已带换行）；
      - 分隔符行中注释槽消费空后即删（`_cleanup_sep_slot`）。
    """
    cfg = _JoinCfg.from_expr(expr)
    items = renderer._resolve_items(node, expr.get("items"))
    rendered = _render_join_items(items, parent_layout, renderer)
    if not rendered:
        return None

    sep_ia = _take_sep_inline_after(node, cfg.sep_anchor)
    result = _assemble_join(rendered, cfg, sep_ia, renderer)
    _cleanup_sep_slot(node, cfg.sep_anchor)

    if cfg.suffix:
        result.append(Text(cfg.suffix))

    if cfg.is_newline_sep or cfg.no_sep or cfg.no_soft:
        doc = Concat(result)
    else:
        doc = group(Concat(result))
    if cfg.nest_level:
        doc = Nest(renderer._indent(cfg.nest_level), doc)
    return doc

