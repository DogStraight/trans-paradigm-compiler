"""Transform 引擎 — 配置驱动的 AST 变换管线

设计原则：
  原语优先 — lookup / foreach / emit / replace 覆盖大多数降级场景
  handler 兜底 — 自定义 Python 函数处理原语无法表达的逻辑
  配置驱动 — transform 配置写在规则 TOML 的 [RuleName.transform] 中

用法:
    from transform.post.engine import ConfigDrivenTransform, transform_handler

    # 1. 注册自定义 handler（可选）
    @transform_handler("my_handler")
    def my_handler(node, scope, ctx):
        ...

    # 2. 创建配置驱动变换插件
    transformer = AstTransformer()
    transformer.register(ConfigDrivenTransform(
        rules=grammar_rules,
        ext_dir="grammar/rules_verilog_ext",
    ))
    ast = transformer.transform(ast, scope)
"""

from .engine import ConfigDrivenTransform
from .registry import transform_handler, get_handler, TransformContext, SKIP

__all__ = [
    "ConfigDrivenTransform",
    "transform_handler",
    "get_handler",
    "TransformContext",
    "SKIP",
]
