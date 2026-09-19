"""line 原语 — 行布局

Doc: renderer/renderer_architecture.md（Line/Break 换行原语）
"""
from typing import Any
from dataclasses import dataclass, field
from core.define import Node
from ..doc import (
    Doc,
    Empty,
    Text,
    Line as SoftLine,
    HardBreak,
    LineBreak,
    Concat,
    Nest,
    group,
)
from .registry import register


@dataclass
class _LineState:
    """line 原语一次装配的状态（跨元素复用）。

    `ia_slots` 是**节点槽位本体的引用**（不复制）——消费即 `del` 防重复消费，
    这是注释节点模型 2b-2 的刻意设计，抽状态类时必须保持同一对象（复制后
    删除不回传节点，注释会被后续路径重复消费）。
    """

    parts: list[Doc] = field(default_factory=list)
    pending_nest: int = 0  # 累积缩进：断行缩进整体 Nest 其后的元素
    has_soft: bool = False  # 出现过软断行 → 整串需 group（可折叠）
    absorb_space: bool = False  # ref 锚命中后吸收紧随的纯空格分隔元素
    ia_slots: dict = field(default_factory=dict)  # inline_after：锚 token → [(注释, 源行)]


def _append_break(state: _LineState, e: dict, renderer: Any) -> None:
    """断行元素 → 三态原语（见 doc.py）：soft 可折叠 / break 组断开时断 /
    hard_break 永远断且强制所在组断开。

    缩进级 > 0 时累计到 `pending_nest`：断行的缩进作用于其**之后**的元素
    （整体 Nest），而不是断行本身。
    """
    indent_level = e.get("indent", 0)
    extra_indent = renderer._indent(indent_level)
    if e.get("hard_break"):
        state.parts.append(HardBreak(extra_indent))
    elif e.get("break"):
        state.parts.append(LineBreak(extra_indent))
    else:
        state.parts.append(SoftLine(extra_indent))
    state.has_soft = True
    if indent_level > 0:
        state.pending_nest += extra_indent


def _insert_str_anchor(state: _LineState, e: str) -> None:
    """字符串元素含锚 token → 后插行中注释。

    字符串元素：布局字符串自带分隔空格（如 `" = "`），注释后补一个空格接后续元素。
    """
    if not state.ia_slots:
        return
    for anchor, entries in list(state.ia_slots.items()):
        if anchor in e:
            for text, _ in entries:
                state.parts.append(Text(text))
                state.parts.append(Text(" "))
            del state.ia_slots[anchor]
            break


def _insert_ref_anchor(state: _LineState, e: dict, node: Node) -> None:
    """ref 元素指向字符串属性（ADR-0013 决策 5）→ 后插行中注释。

    BinaryOp/UnaryOp 的 op 是 `{ref=op}` 属性（如 `+`）——锚 token 匹配属性值
    （如 `a + /* c */ b` 的锚 `+`）。op 无自带空格：注释前后各补空格，并吸收
    布局里 op 后的纯空格分隔元素（防双空格；UnaryOp layout 无分隔元素时自然
    不 absorb）。
    """
    if not state.ia_slots:
        return
    ref_name = e.get("ref")
    if not isinstance(ref_name, str):
        return
    val = getattr(node, ref_name, None)
    if not isinstance(val, str):
        return
    for anchor, entries in list(state.ia_slots.items()):
        if anchor in val:
            for text, _ in entries:
                state.parts.append(Text(" " + text + " "))
            del state.ia_slots[anchor]
            state.absorb_space = True
            break


def _append_element(
    state: _LineState, e: Any, node: Node, parent_layout: dict | None, renderer: Any
) -> None:
    """普通元素：求值 → 补 `pending_nest` → 追加 → 行中注释锚定位。"""
    d = renderer._eval(e, node, parent_layout)
    if d is None:
        return
    if not isinstance(d, Empty):
        if state.pending_nest > 0:
            d = Nest(state.pending_nest, d)
            state.pending_nest = 0
        state.parts.append(d)
    if isinstance(e, str):
        _insert_str_anchor(state, e)
    elif isinstance(e, dict):
        _insert_ref_anchor(state, e, node)


@register("line")
def eval_line(expr: dict, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc | None:
    """line 元素序列 → Doc：断行三态 + 元素求值 + 行中注释定位。

    行中注释 token 标注定位（注释节点模型 2b-2）：inline_after = {锚 token:
    [(注释, 源行号)]}，锚 token 是注释前的 token（如 `assign b = /* c */ rst_n`
    的 `=`）。在布局 line 元素序列里，遇到含锚 token 的文本元素 → 后插注释
    （`=` 后输出）。
    """
    nest_level = expr.get("nest", 0)
    node_slots = getattr(node, "_comment_slots", None) or {}
    state = _LineState(ia_slots=node_slots.get("inline_after", {}) or {})

    for e in expr["line"]:
        if state.absorb_space and isinstance(e, str) and not e.strip():
            state.absorb_space = False
            continue
        if isinstance(e, dict) and (
            e.get("soft") or e.get("break") or e.get("hard_break")
        ):
            _append_break(state, e, renderer)
        else:
            _append_element(state, e, node, parent_layout, renderer)

    if not state.parts:
        return None

    doc: Doc = Concat(state.parts)
    if state.has_soft:
        doc = group(doc)
    if nest_level:
        doc = Nest(renderer._indent(nest_level), doc)
    return doc

