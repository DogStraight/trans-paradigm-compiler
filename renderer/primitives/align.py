"""align 原语 — 绝对列对齐（ADR-0006 阶段 2 新增）

TOML 形态：
    { align = 5, doc = { line = [...] } }

align 的值为"级别数"（× _INDENT_STR 得绝对列），语义同 Prettier
align：除首行外所有换行的缩进列 = max(当前缩进列, 对齐列)。
用于跨行对齐场景（端口声明 name 列等）——group 二元模型表达不了的
"组内列宽统一"由 Align 给出基准列。
Doc: renderer/renderer_architecture.md（Align 绝对列对齐原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Align
from .registry import register


@register("align")
def eval_align(expr: dict, node: Node, parent_layout: dict | None,
               renderer: Any) -> Doc | None:
    """求值 align 原语（绝对列对齐）"""
    levels = expr.get("align", 0)
    inner = expr.get("doc")
    if inner is None:
        return None
    inner_doc = renderer._eval(inner, node, parent_layout)
    if inner_doc is None:
        return None
    return Align(renderer._indent(levels), inner_doc)
