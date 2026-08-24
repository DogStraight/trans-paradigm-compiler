"""indent 原语 — 缩进"""
from typing import Any
from core.define import Node
from ..doc import Doc, Concat, Nest
from .registry import register


@register("indent")
def eval_indent(expr: dict, node: Node, indent: int,
                parent_layout: dict | None, renderer: Any) -> Doc | None:
    del expr, parent_layout  # 原语注册协议签名参数，本原语不消费
    body_docs = renderer._render_body(node, indent + 1)
    if not body_docs:
        return None
    return Nest(len(renderer._INDENT_STR), Concat(body_docs))
