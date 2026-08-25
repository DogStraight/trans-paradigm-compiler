"""text 原语 — 字面量文本"""
from typing import Any
from core.define import Node
from ..doc import Doc, Text


def eval_text(expr: str, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc:
    del node, parent_layout, renderer  # 原语注册协议签名参数，本原语不消费
    return Text(expr)
