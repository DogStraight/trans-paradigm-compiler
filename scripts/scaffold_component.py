#!/usr/bin/env python3
"""Scaffold a new component: pyv new component <name> [--lang lang]"""

import os
import sys
import argparse

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMPONENT_DIR = os.path.join(
    _PROJECT_ROOT, "grammar", "rules_verilog_ext", "_components"
)

COMPONENT_TOML_TPL = """\
[component]
name = "{name}"
lang = "{lang}"
description = "{desc}"
requires = []

[component.grammar]
files = ["00_{name}.toml"]

[component.analyzer]
primitive_order = []
primitives = []
handlers = ["_{name}.py"]

[component.transform]
slots = []
handlers = []
"""

GRAMMAR_TOML_TPL = """\
# {name} — {desc}
"""

HANDLER_PY_TPL = """# {name} — {desc}
\"\"\"Component handler for {name}.\"\"\"

from core.define import Node


def process(node: Node, ctx: dict) -> Node | None:
    \"\"\"Process a node. Return modified node or None to delete.\"\"\"
    return node
"""

TEST_V_TPL = """\
// {name} — {desc}
// Test file for the {name} component.
"""


def scaffold_component(name: str, lang: str = "verilog", desc: str = "") -> None:
    if not name.replace("_", "").isidentifier():
        print(f"[error] invalid component name: {name!r}")
        sys.exit(1)

    desc = desc or f"{name} component for {lang}"

    c_dir = os.path.join(_COMPONENT_DIR, name)
    if os.path.exists(c_dir):
        print(f"[error] component already exists: {c_dir}")
        sys.exit(1)

    os.makedirs(c_dir)

    # component.toml
    with open(os.path.join(c_dir, "component.toml"), "w", encoding="utf-8") as f:
        f.write(COMPONENT_TOML_TPL.format(name=name, lang=lang, desc=desc))

    # Grammar file
    with open(os.path.join(c_dir, f"00_{name}.toml"), "w", encoding="utf-8") as f:
        f.write(GRAMMAR_TOML_TPL.format(name=name, desc=desc))

    # Handler
    with open(os.path.join(c_dir, f"_{name}.py"), "w", encoding="utf-8") as f:
        f.write(HANDLER_PY_TPL.format(name=name, desc=desc))

    print(f"[ok] Created component '{name}' at {c_dir}")
    print(f"      {c_dir}/component.toml")
    print(f"      {c_dir}/00_{name}.toml")
    print(f"      {c_dir}/_{name}.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new PyV component")
    parser.add_argument("name", help="Component name (snake_case)")
    parser.add_argument(
        "--lang", default="verilog", help="Target language (default: verilog)"
    )
    parser.add_argument("--desc", default="", help="Component description")
    args = parser.parse_args()
    scaffold_component(args.name, args.lang, args.desc)


if __name__ == "__main__":
    main()
