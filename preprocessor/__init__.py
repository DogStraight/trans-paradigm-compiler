"""Preprocessor — TOML-driven Verilog macro expansion and reversal.

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse
"""

from ._expand import preprocess, scan_directives, expand_tokens
from ._reverse import reverse_macros, protect_and_reverse
from ._config import load_macro_config

__all__ = [
    "preprocess", "scan_directives", "expand_tokens",
    "reverse_macros", "protect_and_reverse", "load_macro_config",
]
