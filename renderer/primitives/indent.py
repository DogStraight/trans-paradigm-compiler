"""indent 原语 — 缩进

Doc: renderer/renderer_architecture.md（缩进统一模型）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Concat, Nest
from .registry import register


@register("indent")
def eval_indent(expr: dict, node: Node, parent_layout: dict | None,
                renderer: Any) -> Doc | None:
    del expr, parent_layout  # 原语注册协议签名参数，本原语不消费
    body_docs = renderer._render_body(node)
    if not body_docs:
        return None
    return Nest(renderer._indent(1), Concat(body_docs))
