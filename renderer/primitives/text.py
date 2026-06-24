"""
text 原语 — 字面量文本

TOML 表示:
    "some literal text"
    ";"
"""

from typing import Any, Optional
from core.define import Node
from ..doc import Doc, Text


def eval_text(
    expr: str,
    node: Node,
    indent: int,
    parent_layout: Optional[dict],
    renderer: Any,
) -> Doc:
    """求值 text 原语: 字符串字面量 → Text Doc"""
    return Text(expr)
