"""analyzer/primitives/ — 分析器原语包

分析器原语是语言无关的可组合构建块，注册到全局注册表后，
由 SemanticAnalyzer 在 AST 遍历时根据 TOML 配置自动分派。

文件结构:
    registry.py      — 原语注册中心（register/get/@register）
    scope.py         — scope_enter / scope_exit 原语
    symbol.py        — symbol_declare 原语 + capture 提取
    identifier.py    — identifier_resolve 原语
    resolve.py       — resolve_refs 原语（引用展开→变换回调）
    _utils.py        — 共享工具函数（scope 查找/模板解析/名称提取）

原语管线顺序（由 semantic_analyzer.py _PRIMITIVE_ORDER 定义）:
    1. symbol_declare      — 声明符号（注册到父作用域）
    2. scope_enter         — 进入新作用域
    3. identifier_resolve  — 解析标识符引用
    4. [自定义原语]         — 由 TOML primitives 列表声明
    5. 递归子节点
    6. scope_exit          — 退出作用域

扩展方式:
    自定义原语只需 @register 注册，即可在 TOML 中引用。
    无需修改 SemanticAnalyzer 代码。
"""

from .registry import (
    register_primitive,
    get_primitive,
    has_primitive,
    list_primitives,
    register,
    analyzer_primitive,  # 向下兼容
    AnalyzerPrimitive,
)
from .scope import scope_enter, scope_exit
from .symbol import symbol_declare, register_capture_hook
from .identifier import identifier_resolve
from .resolve import resolve_refs
from ._utils import (
    resolve_name,
    find_symbol_in_scope,
    get_attrs_list,
    match_marker,
    find_child_scope,
    resolve_template,
    build_context,
    build_callback,
)

# 确保原语在 import 时自动注册
# (各原语模块的 @register 装饰器在 import 时自动执行注册)

__all__ = [
    "register_primitive",
    "get_primitive",
    "has_primitive",
    "list_primitives",
    "register",
    "analyzer_primitive",
    "AnalyzerPrimitive",
    "register_capture_hook",
    "scope_enter",
    "scope_exit",
    "symbol_declare",
    "identifier_resolve",
]
