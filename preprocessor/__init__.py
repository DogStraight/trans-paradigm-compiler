"""Preprocessor — TOML-driven Verilog macro expansion and reversal.

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse
"""

from ._expand import scan_directives, expand_tokens
from ._reverse import protect_and_reverse
from ._config import load_macro_config

__all__ = [
    "scan_directives", "expand_tokens",
    "protect_and_reverse", "load_macro_config",
]
