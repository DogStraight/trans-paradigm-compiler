"""diagnostic.py — 结构化诊断

兼容 LSP Diagnostic 格式，支持级别（severity）、错误码（code）；
位置通过关联的 AST 节点（node）提供，无独立 position 字段。
"""

from core.define import Node


class Diagnostic:
    """结构化的诊断信息

    Attributes:
        message:   人类可读的错误描述
        code:      错误码（如 "E001"），用于分类和国际化
        level:     级别: "error" / "warning" / "info"
        node:      关联的 AST 节点（用于定位）
    """

    def __init__(
        self,
        message: str,
        code: str = "",
        level: str = "error",
        node: Node | None = None,
    ):
        self.message = message
        self.code = code
        self.level = level
        self.node = node

    def __str__(self) -> str:
        prefix = f"[{self.level}]" if self.level != "error" else "[ERROR]"
        code_str = f"({self.code}) " if self.code else ""
        node_str = f" @{self.node.node_name}" if self.node else ""
        return f"{prefix} {code_str}{self.message}{node_str}"

    def __repr__(self) -> str:
        return self.__str__()

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "code": self.code,
            "level": self.level,
            "node_name": self.node.node_name if self.node else "",
        }
