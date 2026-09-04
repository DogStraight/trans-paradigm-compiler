"""diagnostic.py — 结构化诊断

兼容 LSP Diagnostic 格式，支持级别（severity）、错误码（code）；
位置通过关联的 AST 节点（node）提供，无独立 position 字段。
Doc: analyzer/semantic_checks.md（Diagnostic + related 链）
"""

from core.define import Node


class Diagnostic:
    """结构化的诊断信息

    Attributes:
        message:   人类可读的错误描述
        code:      错误码（如 "E001"），用于分类和国际化
        level:     级别: "error" / "warning" / "info"
        node:      关联的 AST 节点（用于定位）
        related:   关联位置链（LSP relatedInformation 式）——
                   [(message, node), ...]，承载链级溯源（如赋值链/跨文件
                   模块定义处）。node 可跨文件（定位信息在 node._pos_*）。
    """

    def __init__(
        self,
        message: str,
        code: str = "",
        level: str = "error",
        node: Node | None = None,
        related: list | None = None,
    ):
        self.message = message
        self.code = code
        self.level = level
        self.node = node
        self.related: list = related or []

    def __str__(self) -> str:
        prefix = f"[{self.level}]" if self.level != "error" else "[ERROR]"
        code_str = f"({self.code}) " if self.code else ""
        node_str = f" @{self.node.node_name}" if self.node else ""
        return f"{prefix} {code_str}{self.message}{node_str}"

    def __repr__(self) -> str:
        return self.__str__()

    def to_dict(self) -> dict:
        d = {
            "message": self.message,
            "code": self.code,
            "level": self.level,
            "node_name": self.node.node_name if self.node else "",
            "line": getattr(self.node, "_pos_line", None) if self.node else None,
            "column": getattr(self.node, "_pos_col", None) if self.node else None,
        }
        if self.related:
            d["related"] = [
                {
                    "message": msg,
                    "node_name": nd.node_name if nd else "",
                    "line": getattr(nd, "_pos_line", None) if nd else None,
                    "column": getattr(nd, "_pos_col", None) if nd else None,
                }
                for msg, nd in self.related
            ]
        return d
