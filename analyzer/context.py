"""context.py — AnalysisContext

The "black box" data bus between primitives during analysis traversal.
All state is passed through this object; primitives hold no global state.

Responsibilities:
    Carry current AST node, scope, global state, and diagnostics.
    Primitive signature: prim(analyzer, node, context, config).
Doc: analyzer/semantic_checks.md（分析上下文/诊断上报）
"""

from typing import Any
from core.define import Node
from .scope import Scope
from .diagnostic import Diagnostic


class AnalysisContext:
    """分析上下文——原语与框架之间的数据总线

    Attributes:
        node:          当前正在访问的 AST 节点
        scope:         当前作用域
        root_scope:    根作用域
        config:        当前节点的 analyzer 配置
        diagnostics:   已收集的诊断列表
        extra:         扩展数据（供语言专用原语传递临时状态）
    """

    def __init__(
        self,
        node: Node | None = None,
        scope: Scope | None = None,
        root_scope: Scope | None = None,
        config: dict | None = None,
    ):
        self.node = node
        self.scope = scope
        self.root_scope = root_scope
        self.config = config or {}
        self.diagnostics: list[Diagnostic] = []
        self.extra: dict[str, Any] = {}

    def report(
        self,
        message: str,
        code: str = "",
        level: str = "error",
        node: Node | None = None,
        related: list | None = None,
    ) -> None:
        """报告一条诊断信息

        node: 定位节点（缺省 = 当前访问节点）；related: 关联位置链
        [(message, node), ...]（链级溯源，node 可跨文件）。
        """
        self.diagnostics.append(Diagnostic(
            message=message,
            code=code,
            level=level,
            node=node if node is not None else self.node,
            related=related,
        ))
