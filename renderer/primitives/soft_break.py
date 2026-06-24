"""
soft / break 原语 — 换行控制

TOML 表示:
    { soft = true }   软换行：flat 模式 → 空格，broken 模式 → 换行
    { break = true }  硬换行：始终强制换行（不受 flat/broken 影响）

支持附加缩进:
    { break = true, indent = 1 }
    { soft = true, indent = 1 }
"""

from typing import Any, Optional
from core.define import Node
from ..doc import Doc, Line as SoftLine, Break
from .registry import register


@register("soft")
def eval_soft(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Doc:
    """求值 soft 原语（软换行）"""
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return SoftLine(indent_level * len(renderer._INDENT_STR))
    return SoftLine()


@register("break")
def eval_break(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Doc:
    """求值 break 原语（硬换行）"""
    indent_level = expr.get("indent", 0)
    if indent_level > 0:
        return Break(indent_level * len(renderer._INDENT_STR))
    return Break()
