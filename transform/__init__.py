"""transform/ — 后阶段 AST 变换管线

文件结构:
    normalizer.py       — AST 规范化
    pipeline.py         — AstTransformer + TransformPlugin 基类
    config_driven.py    — ConfigDrivenTransform（变换引擎）
    semantic_mapping.py — SemanticMappingPlugin（映射表 + 回调消费）
    registry.py         — 原语注册中心
    primitives/         — 变换原语

额外输出:
    mark_extra(name, subtree)      — 插件内调用，标记额外文件
    collect_extra_asts()           — render 前调用，收集所有额外输出
"""

from .pipeline import AstTransformer, TransformPlugin, mark_extra, collect_extra_asts

# 确保注册了 @register_plugin 的模块被导入
# 执行顺序：SemanticMappingPlugin → ComponentSlotPlugin → ConfigDrivenTransform
# SMP 先运行以填充映射表；组件槽位在 CDT 之前扫描 TypedPortDecl
# 组件插件由 grammar/rules_verilog_ext/_components/*/ 下的 handler 注册
from . import semantic_mapping
from . import config_driven

__all__ = [
    "AstTransformer",
    "TransformPlugin",
    "mark_extra",
    "collect_extra_asts",
    "config_driven",
    "semantic_mapping",
]
