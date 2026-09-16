"""soft / break / hard_break 原语 — 换行控制（三态）

三态语义（见 renderer/doc.py）：
  soft       软换行：flat → 空格，broken → 换行
  break      条件换行：flat → 消失，broken → 换行（组断开时在此断）
  hard_break 强制断行：永远换行，**且强制所在组断开**（向上传播）

Doc: renderer/renderer_architecture.md（soft 软换行原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Line as SoftLine, LineBreak, HardBreak
from .registry import register


@register("soft")
def eval_soft(expr: dict, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc:
    """求值 soft 原语（软换行）"""
    del node, parent_layout  # 原语注册协议签名参数，本原语不消费
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return SoftLine(renderer._indent(indent_level))
    return SoftLine()


@register("break")
def eval_break(expr: dict, node: Node, parent_layout: dict | None,
               renderer: Any) -> Doc:
    """求值 break 原语（条件换行：flat 消失，组断开时换行）

    与 `line` 元素里的 `{ break = true }` 同义（那里由 eval_line **内联**
    处理，不走本 dispatch）。强制断行用 `hard_break`。
    """
    del node, parent_layout  # 原语注册协议签名参数，本原语不消费
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return LineBreak(renderer._indent(indent_level))
    return LineBreak()


@register("hard_break")
def eval_hard_break(expr: dict, node: Node, parent_layout: dict | None,
                    renderer: Any) -> Doc:
    """求值 hard_break 原语（强制断行 + 强制所在组断开）。"""
    del node, parent_layout  # 原语注册协议签名参数，本原语不消费
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return HardBreak(renderer._indent(indent_level))
    return HardBreak()
