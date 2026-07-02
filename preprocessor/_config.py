"""Preprocessor config loader — reads base/_macro.toml."""

import tomllib
from pathlib import Path
from core.define import FileManager


def load_macro_config(rules_dir: str) -> dict:
    """Load base/_macro.toml configuration."""
    base = Path(FileManager.get_full_path(rules_dir)) / "base" / "_macro.toml"
    if not base.exists():
        return {}
    with open(base, "rb") as f:
        return tomllib.load(f)
