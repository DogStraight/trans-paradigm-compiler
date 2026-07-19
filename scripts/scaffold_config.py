#!/usr/bin/env python3
"""Scaffold a new PyV project config: pyv init [--lang lang]"""

import os
import sys
import json

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"
)
_DEFAULT = os.path.join(_CONFIG_DIR, "pyv_config.json")


def scaffold_config(lang: str = "verilog") -> None:
    if not os.path.isdir(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR)

    if os.path.isfile(_DEFAULT):
        print(f"[ok] Config already exists: {_DEFAULT}")
        return

    config = {
        "//": "PyV Compiler — project configuration.",
        "//": "grammar.rules_dir points to the language package root.",
        "//": "Each language package has its own pyv.toml with engine interface config.",
        "grammar": {
            "rules_dir": f"grammar/{lang}",
            "ext_dirs": [f"grammar/{lang}/ext"],
        },
        "pipeline": {
            "stages": ["lex", "parse", "normalize", "analyze", "transform", "render"],
            "default_test": "led_blinker",
        },
    }

    with open(_DEFAULT, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
        f.write("\n")

    print(f"[ok] Created config: {_DEFAULT}")
    print(f"      language: {lang}")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "verilog"
    scaffold_config(lang)
