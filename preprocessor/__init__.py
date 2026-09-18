"""Preprocessor — TOML-driven macro expansion and reversal（语言无关）。

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse
Doc: preprocessor/README.md
"""

from core.config_registry import config_refs_for
from . import _expand, _reverse
from ._expand import scan_directives, expand_tokens, enumerate_conditions
from ._reverse import protect_and_reverse, restore_condition_blocks

__all__ = [
    "scan_directives",
    "expand_tokens",
    "enumerate_conditions",
    "protect_and_reverse",
    "restore_condition_blocks",
    "get_config_refs",
    "_expand",
    "_reverse",
]


def get_config_refs() -> dict[str, str]:
    """返回本部件所有配置需求: { "namespace.key": "_xxx_cfg", ... }"""
    return config_refs_for(__name__)
