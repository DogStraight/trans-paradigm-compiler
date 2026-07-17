"""transform/ — post-phase AST transform pipeline.

Files:
    pipeline.py         — AstTransformer + TransformPlugin base class
    config_driven.py    — ConfigDrivenTransform (transform engine)
    registry.py         — primitive registry (legacy re-export)
    primitives/         — transform primitives
    plugins/            — built-in transform plugins

Language-specific plugins are registered by component handlers
(grammar/<lang>/ext/_components/*/).
The engine itself contains no language-specific knowledge.

Extra output:
    mark_extra(name, subtree)      — called from plugins to mark extra files
    collect_extra_asts()           — called before render to collect extras
"""

from .pipeline import AstTransformer, TransformPlugin, mark_extra, collect_extra_asts

# Load built-in transform plugins (must happen after load_all_components()
# so component plugins register before engine plugins).
from . import config_driven  # noqa: F401 — triggers @register_plugin
from . import plugins  # noqa: F401 — loads _semantic_mapping.py

__all__ = [
    "AstTransformer",
    "TransformPlugin",
    "mark_extra",
    "collect_extra_asts",
    "config_driven",
    "plugins",
]
