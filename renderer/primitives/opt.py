"""opt 原语 — 条件可选

Doc: docs/renderer_architecture.md（opt 可选元素原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Empty
from .registry import register


@register("opt")
def eval_opt(expr: dict, node: Node, parent_layout: dict | None,
             renderer: Any) -> Doc:
    inner = expr["opt"]

    # 检查引用是否缺失
    if isinstance(inner, dict):
        refs = []
        if "line" in inner:
            for e in inner["line"]:
                if isinstance(e, dict) and "ref" in e:
                    refs.append(e["ref"])
                if isinstance(e, dict) and "join" in e and "items" in e:
                    refs.append(e["items"])
        if "ref" in inner:
            refs.append(inner["ref"])
        if "join" in inner and "items" in inner:
            refs.append(inner["items"])

        for ref in refs:
            if getattr(node, ref, None) is None:
                return Empty()

    inner_doc = renderer._eval(inner, node, parent_layout)
    return inner_doc if inner_doc is not None else Empty()
