"""suffix_when 原语 — 值条件后缀（输出配置动态化）

语言包声明"节点属性值满足条件时追加后缀文本"。引擎零语言知识：
条件（startswith 等字符串判定）与后缀都是数据，由布局 TOML 提供。

典型用途（verilog 语言包）：
    [Identifier.renderer.layout]
    line = [
      { ref = "content" },
      { suffix_when = { startswith = "\\\\" }, attr = "content", text = " " },
    ]

转义标识符（`\\$_BUF_`）须以空白终止（IEEE 1364 A.9.3）——渲染器在
值带 `\\` 前缀的标识符后补空格（`module \\$_BUF_ (`），否则输出
`\\$_BUF_(` 名字被读成 `\\$_BUF_(`（错误标识符）。普通标识符条件不命中，
输出零变化。

条件不命中 / 属性非字符串 → 返回 None（line 原语跳过）。
Doc: docs/decisions/0007-pipeline-schedule.md（同批输出缺陷修复，见 ADR 附注）
"""

from typing import Any
from core.define import Node
from ..doc import Doc, Text
from .registry import register


@register("suffix_when")
def eval_suffix_when(
    expr: dict, node: Node, parent_layout: dict | None, renderer: Any
) -> Doc | None:
    """条件成立时输出后缀文本，否则 None。"""
    del parent_layout, renderer  # 原语注册协议签名参数，本原语不消费
    cond = expr.get("suffix_when")
    if not isinstance(cond, dict):
        return None
    val = getattr(node, expr.get("attr", "content"), None)
    if not isinstance(val, str):
        return None
    prefix = cond.get("startswith")
    if prefix and val.startswith(prefix):
        return Text(expr.get("text", " "))
    return None
