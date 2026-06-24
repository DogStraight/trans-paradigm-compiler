"""
indent 原语 — 缩进

TOML 表示:
    { indent = true }
    { indent = ["@body"] }

等价于: 子内容增加一级缩进。
在 TOML 中通常用于 body 描述。
"""

from typing import Any, Optional
from core.define import Node
from ..doc import Doc, Concat, Nest
from .registry import register


@register("indent")
def eval_indent(
    expr: dict,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Optional[Doc]:
    """求值 indent 原语"""
    body_docs = renderer._render_body(node, indent + 1)
    if not body_docs:
        return None
    return Nest(len(renderer._INDENT_STR), Concat(body_docs))
