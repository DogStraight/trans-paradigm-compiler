"""context.py — 分析上下文（AnalysisContext）

分析器遍历过程中的"黑匣子"，是原语/槽位之间唯一的通信介质。
所有状态通过此对象传递，原语不持有任何全局变量。

职责：
    承载当前 AST 节点、作用域、全局状态、诊断信息。
    原语签名统一为 prim(analyzer, node, context, config)。
"""

from typing import Any, Optional, List
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
        node: Optional[Node] = None,
        scope: Optional[Scope] = None,
        root_scope: Optional[Scope] = None,
        config: Optional[dict] = None,
    ):
        self.node = node
        self.scope = scope
        self.root_scope = root_scope
        self.config = config or {}
        self.diagnostics: List[Diagnostic] = []
        self.extra: dict[str, Any] = {}

    def report(self, message: str, code: str = "", level: str = "error") -> None:
        """报告一条诊断信息"""
        self.diagnostics.append(Diagnostic(
            message=message,
            code=code,
            level=level,
            node=self.node,
        ))
