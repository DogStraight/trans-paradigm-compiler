"""transform/ — 后阶段 AST 变换管线

文件结构:
    normalizer.py       — AST 规范化（pre 阶段）
    pipeline.py         — AstTransformer + TransformPlugin 基类
    config_driven.py    — ConfigDrivenTransform（配置驱动变换引擎）
    semantic_mapping.py — SemanticMappingPlugin（语义映射表 + 后处理）
    implicit_decl.py    — ImplicitDeclPlugin（隐式声明）
    registry.py         — 原语注册中心
    primitives/         — 变换原语（内部）
"""

from .pipeline import AstTransformer, TransformPlugin

__all__ = ["AstTransformer", "TransformPlugin"]
