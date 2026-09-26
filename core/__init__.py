"""core — 引擎骨架包。

版本单一来源（TODO P2.2）：运行时/CLI 读这里的 __version__；
pyproject.toml 的 [project].version 与此保持一致
（tests/engine/core/test_version.py 锁定两者一致）。
Doc: core/component_protocol.md（引擎骨架/组件协议）
"""

__version__ = "0.1.3"

from .define import Node, Token, FileManager, GrammarRule, GrammarRulesRegister

__all__ = [
    "Node",
    "Token",
    "FileManager",
    "GrammarRule",
    "GrammarRulesRegister",
    "__version__",
]
