"""service.py — 引擎给插件的**语言无关服务句柄**（ADR-0019 决策 1 的③）。

插件求解器只拿到三样东西：定位命中 / 原子 / 本上下文；它需要的"通用能力"
（渲染子树、读源、行映射…）全部从此处取——**按需开面**，不预先铺满。

P2 只开 `render`（精化项要把 AST 子树取出成值文本）。其余面随对应族搬迁再开：
读源 / 行映射 `line_map` / 宏区间 `macro_regions` 等。

Doc: analyzer/elaboration/README.md
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from core.define import Node


class ServiceApi(Protocol):
    """插件侧看到的服务面（引擎实现 = `ElaborationService`）。"""

    def render(self, node: Node) -> str:
        """AST 子树 → 文本。"""
        ...


class ElaborationService:
    """服务句柄实现：把引擎既有的通用能力转交给插件。

    `render` 的语义**完全等同于** `StructureCtx.render_subtree`（strip；拿不到 →
    空串，调用方按"不可判"保守处理）。此处只**转交**、不重新实现——故不引入新的
    异常处理点（渲染失败即空串是既有且已论证的设计，不是本次新增的吞异常）。
    """

    def __init__(self, render_subtree: Callable[[Node], str]) -> None:
        self._render_subtree = render_subtree

    def render(self, node: Node) -> str:
        """AST 子树 → 文本（宽度表达式 / 参数默认值等值文本）。"""
        return self._render_subtree(node)
