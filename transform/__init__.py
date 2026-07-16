"""transform/ — 后阶段 AST 变换管线

文件结构:
    normalizer.py       — AST 规范化
    pipeline.py         — AstTransformer + TransformPlugin 基类
    config_driven.py    — ConfigDrivenTransform（变换引擎）
    registry.py         — 原语注册中心
    primitives/         — 变换原语

语言专用插件由 grammar/rules_verilog_ext/_components/*/ 下的 handler 注册。
引擎本身不含任何语言知识。

额外输出:
    mark_extra(name, subtree)      — 插件内调用，标记额外文件
    collect_extra_asts()           — render 前调用，收集所有额外输出
"""

from .pipeline import AstTransformer, TransformPlugin, mark_extra, collect_extra_asts

# 插件注册由各组件 handler 和 run_pipeline.py 处理
# transform/ 本身只提供基础架构，不含具体插件

__all__ = [
    "AstTransformer",
    "TransformPlugin",
    "mark_extra",
    "collect_extra_asts",
]
