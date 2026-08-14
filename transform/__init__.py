"""transform/ — post-phase AST transform pipeline.

Files:
    normalizer.py          — AST normalization (parser output → canonical form)
    engine.py              — AstTransformer + TransformPlugin base class
    config_driven.py       — ConfigDrivenTransform (transform engine)
    _semantic_mapping.py   — SemanticMappingPlugin (mapping table builder)
    registry.py            — primitive registry (legacy re-export)
    primitives/            — transform primitives

Language-specific plugins are registered by component handlers
(grammar/<lang>/ext/_components/*/).
The engine itself contains no language-specific knowledge.

Extra output:
    mark_extra(name, subtree)      — called from plugins to mark extra files
    collect_extra_asts()           — called before render to collect extras
"""

from .engine import AstTransformer, TransformPlugin, mark_extra, collect_extra_asts

# 加载内置变换插件（必须在 load_all_components() 之后，保证组件插件先于引擎插件注册）
# 顺序要求：SemanticMappingPlugin（建映射表）必须先于 ConfigDrivenTransform（消费映射表）
from . import _semantic_mapping  # noqa: F401 — triggers @register_plugin
from . import config_driven  # noqa: F401 — triggers @register_plugin

__all__ = [
    "AstTransformer",
    "TransformPlugin",
    "mark_extra",
    "collect_extra_asts",
    "config_driven",
    "_semantic_mapping",
]
