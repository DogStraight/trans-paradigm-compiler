"""analyzer/primitives/ — 分析器原语包

分析器原语是语言无关的可组合构建块，注册到全局注册表后，
由 SemanticAnalyzer 在 AST 遍历时根据 TOML 配置 [RuleName.analyzer] 自动分派。

内置原语:
    scope_enter        — 进入新作用域
    scope_exit         — 退出当前作用域
    symbol_declare     — 声明符号（含 capture 属性提取）
    identifier_resolve — 解析标识符引用

注册方式:
    @analyzer_primitive("my_primitive")
    def my_primitive(analyzer, node, config):
        ...

使用方式:
    TOML 中 [RuleName.analyzer] 配置会自动触发对应原语，
    无需手动调用原语函数。

扩展:
    自定义原语只需注册到全局注册表，即可在任意 TOML 规则中通过
    analyzer 配置引用。无需修改 SemanticAnalyzer 代码。
"""

from .registry import (
    register_primitive,
    get_primitive,
    has_primitive,
    list_primitives,
    analyzer_primitive,
    AnalyzerPrimitive,
)
from .scope import scope_enter, scope_exit
from .symbol import symbol_declare, identifier_resolve, register_capture_hook

# 确保原语在 import 时自动注册
# (各原语模块的 @analyzer_primitive 装饰器在 import 时自动执行注册)

__all__ = [
    "register_primitive",
    "get_primitive",
    "has_primitive",
    "list_primitives",
    "analyzer_primitive",
    "AnalyzerPrimitive",
    "register_capture_hook",
    "scope_enter",
    "scope_exit",
    "symbol_declare",
    "identifier_resolve",
]
