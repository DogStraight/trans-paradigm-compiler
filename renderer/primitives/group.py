"""group 原语 — flat/broken 二象性

Doc: renderer/renderer_architecture.md（group/flatten 二象性）
"""

from typing import Any
from core.define import Node
from ..doc import Doc, Empty, Concat, group
from .registry import register


@register("group")
def eval_group(
    expr: dict, node: Node, parent_layout: dict | None, renderer: Any
) -> Doc | None:
    parts: list[Doc] = []
    for e in expr["group"]:
        d = renderer._eval(e, node, parent_layout)
        if d is None:
            return None  # 真正的缺失（非 opt 包裹的 ref），整体无意义
        if not isinstance(d, Empty):
            parts.append(d)

    if not parts:
        return None
    return group(Concat(parts))
