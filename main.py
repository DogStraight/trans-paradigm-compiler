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

    else:
        print(f"Unknown command: {command}")
        _print_usage()
        sys.exit(1)


def _print_usage() -> None:
    print("Usage: python main.py <command> [args...]")
    print()
    print("Commands:")
    print("  pipeline [test_name]  运行 Verilog 编译管线")
    print("  linter [input_file]   运行语法扫描器")


if __name__ == "__main__":
    main()
