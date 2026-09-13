"""line_suffix 原语 — 行尾锚定（ADR-0006 阶段 2 新增）

TOML 形态：
    { line_suffix = " // note" }

内容推迟到"下一个换行点之前"输出（行尾注释锚定），layout() 入口
经 _resolve_line_suffix 重写为换行前的 Text。
与 inline_comment.py（现仅 tpc marker 内部通道）互补：前者是 Doc
一等公民，后者是渲染后字符串级后处理。
Doc: renderer/renderer_architecture.md（LineSuffix 行尾锚定原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, LineSuffix
from .registry import register


@register("line_suffix")
def eval_line_suffix(expr: dict, node: Node, parent_layout: dict | None,
                     renderer: Any) -> Doc:
    """求值 line_suffix 原语（行尾注释锚定）"""
    del node, parent_layout, renderer  # 原语注册协议签名参数，本原语不消费
    return LineSuffix(expr.get("line_suffix", ""))
