"""soft / break 原语 — 换行控制"""
from typing import Any
from core.define import Node
from ..doc import Doc, Line as SoftLine, Break
from .registry import register


@register("soft")
def eval_soft(expr: dict, node: Node, indent: int,
              parent_layout: dict | None, renderer: Any) -> Doc:
    """求值 soft 原语（软换行）"""
    del node, indent, parent_layout  # 原语注册协议签名参数，本原语不消费
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return SoftLine(indent_level * len(renderer._INDENT_STR))
    return SoftLine()


@register("break")
def eval_break(expr: dict, node: Node, indent: int,
               parent_layout: dict | None, renderer: Any) -> Doc:
    """求值 break 原语（硬换行）"""
    del node, indent, parent_layout  # 原语注册协议签名参数，本原语不消费
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return Break(indent_level * len(renderer._INDENT_STR))
    return Break()
