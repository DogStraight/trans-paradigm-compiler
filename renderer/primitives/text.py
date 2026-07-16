"""text 原语 — 字面量文本"""
from typing import Any
from core.define import Node
from ..doc import Doc, Text


def eval_text(expr: str, node: Node, indent: int,
              parent_layout: dict | None, renderer: Any) -> Doc:
    return Text(expr)
