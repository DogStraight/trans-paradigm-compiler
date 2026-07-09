"""transform/ — 后阶段 AST 变换管线

文件结构:
    normalizer.py       — AST 规范化
    pipeline.py         — AstTransformer + TransformPlugin 基类
    config_driven.py    — ConfigDrivenTransform（变换引擎）
    semantic_mapping.py — SemanticMappingPlugin（映射表 + 回调消费）
    registry.py         — 原语注册中心
    primitives/         — 变换原语
"""

from .pipeline import AstTransformer, TransformPlugin

__all__ = ["AstTransformer", "TransformPlugin"]
