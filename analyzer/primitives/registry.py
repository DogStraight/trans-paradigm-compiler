"""registry.py — 分析器原语注册中心

与 transform/post/engine/registry.py 对称设计，但职责分离。
分析器原语负责 AST 遍历期间的语义分析行为（作用域、符号、引用解析），
变换原语负责后阶段的 AST 修改（展开、替换、删除）。

注册的原语会注入到 SemanticAnalyzer._walk_node 的管线中，
按 TOML 配置 [RuleName.analyzer] 的声明顺序依次执行。
"""

from typing import Callable, Optional, Any
from core.define import Node


# ── 原语签名 ──
#
# AnalyzerPrimitive = Callable[
#     analyzer: SemanticAnalyzer,    # 分析器实例（持有 scope/errors 状态）
#     node: Node,                    # 当前 AST 节点
#     config: dict,                  # 该规则 analyzer 配置字典
# ] -> None
#
# 原语通过副作用修改 analyzer 的内部状态（scope、symbols、errors 等）。

AnalyzerPrimitive = Callable[..., None]

# ── 原语注册表 ──

_primitives: dict[str, AnalyzerPrimitive] = {}


def register_primitive(name: str, fn: AnalyzerPrimitive) -> None:
    """注册一个分析器原语

    Args:
        name: 原语名称，TOML 配置中通过此名称引用
        fn: 原语函数，签名见 AnalyzerPrimitive
    """
    if name in _primitives:
        raise ValueError(f"Analyzer primitive '{name}' 已注册")
    _primitives[name] = fn


def get_primitive(name: str) -> Optional[AnalyzerPrimitive]:
    """按名称获取已注册的原语"""
    return _primitives.get(name)


def has_primitive(name: str) -> bool:
    """检查原语是否已注册"""
    return name in _primitives


def list_primitives() -> list[str]:
    """列出所有已注册的原语名称"""
    return sorted(_primitives.keys())


# ── 装饰器 ──


def analyzer_primitive(name: str) -> Callable:
    """装饰器：注册一个分析器原语

    Usage:
        @analyzer_primitive("scope_enter")
        def scope_enter(analyzer, node, config):
            ...
    """
    def decorator(fn: AnalyzerPrimitive) -> AnalyzerPrimitive:
        register_primitive(name, fn)
        return fn
    return decorator
