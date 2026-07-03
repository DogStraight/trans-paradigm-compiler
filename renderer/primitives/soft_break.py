"""soft / break 原语 — 换行控制"""
from typing import Any, Optional
from core.define import Node
from ..doc import Doc, Line as SoftLine, Break
from .registry import register


@register("soft")
def eval_soft(expr: dict, node: Node, indent: int,
              parent_layout: Optional[dict], renderer: Any) -> Doc:
    """求值 soft 原语（软换行）"""
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return SoftLine(indent_level * len(renderer._INDENT_STR))
    return SoftLine()


@register("break")
def eval_break(expr: dict, node: Node, indent: int,
               parent_layout: Optional[dict], renderer: Any) -> Doc:
    """求值 break 原语（硬换行）"""
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return Break(indent_level * len(renderer._INDENT_STR))
    return Break()
