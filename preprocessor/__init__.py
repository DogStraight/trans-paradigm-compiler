"""Preprocessor — TOML-driven Verilog macro expansion and reversal.

Architecture:
    Source → Preprocessor (expand) → Lexer → Parser → ... → Renderer → Reverse
"""

from ._expand import preprocess
from ._reverse import reverse_macros, protect_and_reverse
from ._config import load_macro_config

__all__ = ["preprocess", "reverse_macros", "protect_and_reverse", "load_macro_config"]
