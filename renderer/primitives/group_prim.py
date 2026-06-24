"""
group 原语 — 组（可能在一行或折行）

TOML 表示:
    { group = [
        " #(",
        { ref = "params" },
        ")",
    ] }

group 会自动尝试 flat 版本（一行），
如果超宽则回退到 broken 版本（保留换行）。
"""

from typing import Any, Optional, List
from core.define import Node
from ..doc import Doc, Empty, Concat, group
from .registry import register


@register("group")
def eval_group(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Optional[Doc]:
    """求值 group 原语"""
    parts: List[Doc] = []
    for e in expr["group"]:
        d = renderer._eval(e, node, indent, parent_layout)
        if d is None:
            return None  # 真正的缺失（非 opt 包裹的 ref），整体无意义
        if not isinstance(d, Empty):
            parts.append(d)

    if not parts:
        return None
    return group(Concat(parts))
