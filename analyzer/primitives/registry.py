"""registry.py — analyzer primitive 注册表。

与 transform/primitives/registry.py 对称设计但职责分离：analyzer 原语在
AST 遍历期间做语义分析（作用域、符号、引用解析）；transform 原语做
阶段后 AST 变换（展开、替换、删除）。

注册的原语注入 AnalysisTraversal 的遍历管线，按 TOML [RuleName.analyzer]
配置中声明的顺序执行。
Doc: analyzer/semantic_checks.md（原语注册机制）
"""

from typing import Callable


# ── 原语签名 ──
#
# AnalyzerPrimitive = Callable[
#     analyzer: AnalysisTraversal,  # 分析器实例（持有 scope/errors）
#     node: Node,                    # 当前 AST 节点
#     config: dict,                  # 本规则的 analyzer 配置字典
# ] -> None
#
# 原语通过副作用修改分析器内部状态（scope、symbols、errors）

AnalyzerPrimitive = Callable[..., None]

# ── 原语注册表 ──

_primitives: dict[str, AnalyzerPrimitive] = {}


def register_primitive(name: str, fn: AnalyzerPrimitive) -> None:
    """注册一个分析器原语（幂等：同名同函数重复注册不报错）。

    Args:
        name: 原语名，TOML [RuleName.analyzer] 配置中引用。
        fn: 原语函数，签名见 AnalyzerPrimitive。

    幂等理由：组件 handler 模块可被**补注册**（注册副作用一次性，但注册表
    可能被外部清理——如测试隔离还原；见 plugin_loader 的 handler 缓存模型）。
    同名但不同函数仍报错（真正的冲突）。
    """
    if name in _primitives:
        if _primitives[name] is fn:
            return
        raise ValueError(f"Analyzer primitive '{name}' 已注册")
    _primitives[name] = fn


def get_primitive(name: str) -> AnalyzerPrimitive | None:
    """按名称取已注册的原语。"""
    return _primitives.get(name)


def has_primitive(name: str) -> bool:
    """检查原语是否已注册。"""
    return name in _primitives


def list_primitives() -> list[str]:
    """列出所有已注册的原语名称"""
    return sorted(_primitives.keys())


# ── 装饰器 ──


def register(name: str) -> Callable:
    """装饰器：注册一个分析器原语。

    与 renderer/primitives/registry.py / transform/primitives/registry.py 统一签名。

    Usage:
        @register("scope_enter")
        def scope_enter(analyzer, node, config):
            ...
    """
    def decorator(fn: AnalyzerPrimitive) -> AnalyzerPrimitive:
        register_primitive(name, fn)
        return fn
    return decorator
