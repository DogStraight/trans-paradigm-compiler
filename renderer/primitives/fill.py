"""fill 原语 — 流式折行（ADR-0006 阶段 2 新增）

TOML 形态：
    { fill = [ {ref="a"}, {soft=true}, {ref="b"}, {soft=true}, {ref="c"} ] }

docs 是 内容/分隔符 交替序列。逐元素贪心放置：
  - 分隔符（通常 soft=true / Line）：当前行放得下 → 空格；放不下 → 换行
  - 内容项：放不下时换行后再放
与 group（整体 flat/broken 二选一）不同：fill 可产生"折了几行、其余
保持一行"的中间态，适合长列表（参数列表、逗号表达式）的自然填充。
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Fill
from .registry import register


@register("fill")
def eval_fill(expr: dict, node: Node, parent_layout: dict | None,
              renderer: Any) -> Doc | None:
    """求值 fill 原语（流式折行）"""
    items = expr.get("fill")
    if not items:
        return None
    parts: list[Doc] = []
    for e in items:
        d = renderer._eval(e, node, parent_layout)
        if d is not None:
            parts.append(d)
    if not parts:
        return None
    return Fill(parts)
