"""structure — 语法配置驱动的语言无关结构推导层。

定位：把"语言包 TOML 规则"推导成**可供消费的分片/结构信息**，不含任何语言字面量，
也不产生诊断。两个消费方：

- `linter/`：反解析器（在 parser 前用 token 流拦问题）——按发现节点注册检查器；
- `islands/`：片段模式——把发现节点当"可进管线的语法岛"候选，water 原样保留。

推导链（逐层单向依赖）：

    setup_grammar（parser）
        → grammar_slicer.build_slice_tree（规则 → 切片树）
        → first_set.first_tokens（FIRST 集，单一实现）
        → lookahead.LookaheadTable（token → 候选规则）
        → discovery.Discovery（块/括号栈 + 前瞻 + [discovery] 声明 → DiscoveredNode 树）

语言事实（容器/延续/属性对/子句分隔符）来自语言包 `[discovery]` 声明
（`discovery_shape.py`；ADR-0025：声明而非猜）。

Doc: structure/README.md
"""

from .discovery import Discovery
from .discovery_shape import DiscoveryShape, is_stmt_container, load_shape
from .first_set import first_tokens
from .grammar_slicer import build_slice_tree
from .lookahead import LookaheadTable, fallback_statement_names
from .node import CTX_TOP, DiscoveredNode, UnrecognizedSite

__all__ = [
    "CTX_TOP",
    "DiscoveredNode",
    "Discovery",
    "DiscoveryShape",
    "LookaheadTable",
    "UnrecognizedSite",
    "build_slice_tree",
    "fallback_statement_names",
    "first_tokens",
    "is_stmt_container",
    "load_shape",
]
