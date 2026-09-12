"""transform — AST 变换（AST → AST，配置驱动 + 插件扩展）。

The engine itself contains no language-specific knowledge; language-specific
plugins are registered via component handlers (grammar/<lang>/plugins/).

Extra output:
    mark_extra(name, subtree)      — called from plugins to mark extra files
    collect_extra_asts()           — called before render to collect extras
Doc: docs/language_walkthrough.md（语义 + 产出：transform）
"""

from .engine import AstTransformer, TransformPlugin, mark_extra, collect_extra_asts

# 加载内置变换插件（必须在 load_all_components() 之后，保证组件插件先于引擎插件注册）
# 顺序要求：SlotRunnerPlugin（槽位执行）与 SemanticMappingPlugin（建映射表）
# 须先于 ConfigDrivenTransform（消费映射表）。
from . import slot_runner  # noqa: F401 — triggers @register_plugin
from . import _semantic_mapping  # noqa: F401 — triggers @register_plugin
from . import config_driven  # noqa: F401 — triggers @register_plugin

__all__ = [
    "AstTransformer",
    "TransformPlugin",
    "mark_extra",
    "collect_extra_asts",
    "config_driven",
    "_semantic_mapping",
    "slot_runner",
]
