"""soft / break / hard_break 原语 — 换行控制（三态）

三态语义（见 renderer/doc.py）：
  soft       软换行：flat → 空格，broken → 换行
  break      条件换行：flat → 消失，broken → 换行（组断开时在此断）
  hard_break 强制断行：永远换行，**且强制所在组断开**（向上传播）

Doc: renderer/renderer_architecture.md（soft 软换行原语）
"""
from collections.abc import Callable
from typing import Any, cast
from core.define import Node
from ..doc import Doc, Line as SoftLine, LineBreak, HardBreak
from .registry import register


def _break_doc(doc_cls: type[Doc], expr: dict, renderer: Any) -> Doc:
    """按 `indent` 配置构造换行 Doc：有缩进 → 带缩进串，否则无参构造。

    三态（soft / break / hard_break）只差 Doc 类型，构造规则同一条。
    """
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        # soft/break/hard_break 三个 Doc 的构造签名同为 (str)
        return cast(Callable[[str], Doc], doc_cls)(renderer._indent(indent_level))
    return doc_cls()


@register("soft")
def eval_soft(expr: dict, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc:
    """求值 soft 原语（软换行）"""
    del node, parent_layout  # 原语注册协议签名参数，本原语不消费
    return _break_doc(SoftLine, expr, renderer)


@register("break")
def eval_break(expr: dict, node: Node, parent_layout: dict | None,
               renderer: Any) -> Doc:
    """求值 break 原语（条件换行：flat 消失，组断开时换行）

    与 `line` 元素里的 `{ break = true }` 同义（那里由 eval_line **内联**
    处理，不走本 dispatch）。强制断行用 `hard_break`。
    """
    del node, parent_layout  # 原语注册协议签名参数，本原语不消费
    return _break_doc(LineBreak, expr, renderer)


@register("hard_break")
def eval_hard_break(expr: dict, node: Node, parent_layout: dict | None,
                    renderer: Any) -> Doc:
    """求值 hard_break 原语（强制断行 + 强制所在组断开）。"""
    del node, parent_layout  # 原语注册协议签名参数，本原语不消费
    return _break_doc(HardBreak, expr, renderer)
