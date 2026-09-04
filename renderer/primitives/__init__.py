"""
primitives/__init__.py — DSL 原语求值器

将 TOML 布局表达式求值为 Doc IR。
每个原语对应一个文件，通过 @register() 装饰器自动注册到调度中心。
Doc: renderer/renderer_architecture.md（布局原语注册表）
"""

from typing import Any
from core.define import Node
from ..doc import Doc, Text

from .registry import get_registry
from .text import eval_text

# 导入所有原语模块，触发 @register 装饰器注册处理函数（副作用 import）。
# _PRIMITIVE_MODULES 元组引用这些模块（表达"原语模块集合"），并在 eval_expr
# 中做防御性校验消费，消除 pylance 对副作用 import 的"未存取"误报。
from . import ref as _ref
from . import join as _join
from . import group as _group
from . import line as _line
from . import indent as _indent
from . import opt as _opt
from . import soft_break as _soft_break
from . import align as _align
from . import fill as _fill
from . import line_suffix as _line_suffix
from . import intent as _intent
from . import suffix_when as _suffix_when

_PRIMITIVE_MODULES = (
    _ref,
    _join,
    _group,
    _line,
    _indent,
    _opt,
    _soft_break,
    _align,
    _fill,
    _line_suffix,
    _intent,
    _suffix_when,
)

__all__ = [
    "eval_text",
    "eval_expr",
    "get_registry",
    "_PRIMITIVE_MODULES",
]


def eval_expr(
    expr: Any,
    node: Node,
    parent_layout: dict | None,
    renderer: Any,  # Renderer 实例，用于回调 _render_inline/_render_body 等
) -> Doc | None:
    """将 TOML 布局表达式求值为 Doc

    Args:
        expr: TOML 表达式（str / dict / list）
        node: 当前 AST 节点
        parent_layout: 父节点的 layout 配置（用于 override）
        renderer: Renderer 实例，提供 _render_inline / _render_body 等方法

    Returns:
        Doc 或 None（当引用缺失时）
    """
    if expr is None:
        return None

    if isinstance(expr, str):
        return eval_text(expr, node, parent_layout, renderer)

    if not isinstance(expr, dict):
        return Text(str(expr))

    # 防御性校验：确认所有原语模块已加载（副作用 import 的注册结果由
    # get_registry 消费；此处引用 _PRIMITIVE_MODULES 保证 import 副作用生效）
    if not _PRIMITIVE_MODULES:
        raise RuntimeError("原语模块未加载")

    for key, handler in get_registry():
        if key in expr:
            return handler(expr, node, parent_layout, renderer)

    return None


__all__ = ["eval_expr"]
