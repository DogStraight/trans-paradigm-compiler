#!/usr/bin/env python3
"""
main.py — PyV Compiler CLI 入口

用法:
    python main.py pipeline [test_name]
    python main.py linter [input_file] [--json]
"""

import sys
import os

# 确保项目根在 sys.path 中
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "pipeline":
        from verilog.run_pipeline import main as pipeline_main

        sys.argv = [sys.argv[0]] + args
        pipeline_main()

    elif command == "linter":
        from linter.cli import cli_main as cli_main

        sys.argv = [sys.argv[0]] + args
        cli_main()

    elif command == "new" and args and args[0] == "component":
        from scripts.scaffold_component import scaffold_component

        name = args[1] if len(args) > 1 else ""
        lang = args[3] if len(args) > 3 and args[2] == "--lang" else "verilog"
        scaffold_component(name, lang)

    else:
        print(f"Unknown command: {command}")
        _print_usage()
        sys.exit(1)


def _print_usage() -> None:
    print("Usage: python main.py <command> [args...]")
    print()
    print("Commands:")
    print("  pipeline [test_name]          Run the Verilog compilation pipeline")
    print("  linter [input_file]           Run the syntax scanner")
    print("  new component <name>          Scaffold a new component")


if __name__ == "__main__":
    main()
