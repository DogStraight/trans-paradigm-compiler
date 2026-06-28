"""
registry.py — Transform handler 注册中心

提供装饰器 @transform_handler(name) 注册自定义 Python handler，
当 TOML 中配置 kind = "custom" 且 handler = "name" 时被引擎调用。

Handler 签名:
    def handler(node: Node, root_scope: Scope, ctx: TransformContext) -> TransformResult

TransformResult 可以是:
    - Node        : 替换当前节点
    - list[Node]  : 替换为多个节点（用于展开场景）
    - None        : 删除当前节点
    - SKIP        : 不变（不修改）
"""

from typing import Callable, Any, Optional
from core.define import Node
from analyzer.scope import Scope


# ── 类型别名 ──

class _Skip:
    """标记值：跳过变换，不修改节点"""
    def __repr__(self):
        return "SKIP"
SKIP = _Skip()

# Handler 返回类型
TransformResult = Node | list[Node] | None | _Skip


class TransformContext:
    """变换上下文，传递给 handler 的附加信息

    Attributes:
        rule_name:   当前节点对应的语法规则名
        config:      当前节点的 transform 配置 dict（整个 [RuleName.transform] 块）
        tables:      引擎加载的所有参考表（类型表等）
        extra:       引擎初始化时传入的额外数据
    """

    def __init__(
        self,
        rule_name: str = "",
        config: Optional[dict] = None,
        tables: Optional[dict] = None,
        extra: Optional[dict] = None,
    ):
        self.rule_name = rule_name
        self.config = config or {}
        self.tables = tables or {}
        self.extra = extra or {}


# Handler 签名
TransformHandler = Callable[[Node, Scope, TransformContext], TransformResult]


# ── 注册中心 ──

_handler_registry: dict[str, TransformHandler] = {}


def transform_handler(name: str):
    """装饰器：注册一个自定义 transform handler

    用法:
        @transform_handler("expand_typed_port")
        def expand_typed_port(node, scope, ctx):
            ...
    """
    def decorator(fn: TransformHandler) -> TransformHandler:
        if name in _handler_registry:
            raise ValueError(f"Transform handler '{name}' 已注册")
        _handler_registry[name] = fn
        return fn
    return decorator


def get_handler(name: str) -> Optional[TransformHandler]:
    """按名称获取已注册的 handler"""
    return _handler_registry.get(name)


def list_handlers() -> list[str]:
    """列出所有已注册的 handler 名称"""
    return list(_handler_registry.keys())
