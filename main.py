#!/usr/bin/env python3
"""
main.py — PyV Compiler CLI entry point

Usage:
    python main.py format <file>                  Format a Verilog file
    python main.py lint <file> [--json]           Lint a Verilog file
    python main.py pipeline [test_name]           Run a single test
    python main.py new component <name>           Scaffold a new component
"""

import sys
import os
import argparse

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _resolve_grammar_dirs() -> tuple[str, list[str]]:
    """Resolve and validate grammar directories from pyv.toml metadata."""
    from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS

    root = _project_root
    rules_dir = os.path.join(root, DEFAULT_RULES_DIR)
    if not os.path.isdir(rules_dir):
        print(f"[fatal] Grammar directory not found: {rules_dir}", file=sys.stderr)
        print(f"        Check grammar/pyv.toml [grammar].rules_dir", file=sys.stderr)
        sys.exit(1)

    ext_dirs = []
    for ed in DEFAULT_EXT_DIRS:
        candidate = os.path.join(root, ed)
        if os.path.isdir(candidate):
            ext_dirs.append(candidate)
        else:
            print(f"[warn] EXT grammar directory not found: {candidate}", file=sys.stderr)

    return rules_dir, ext_dirs


def _cmd_format(args: argparse.Namespace) -> None:
    """pyv format — format a Verilog file through the full pipeline."""
    if not os.path.isfile(args.file):
        print(f"[fatal] File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    from verilog.run_pipeline import run_pipeline_on_source

    rules_dir, ext_dirs = _resolve_grammar_dirs()

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    result = run_pipeline_on_source(
        source=source,
        input_path=args.file,
        out_dir=None,
        quiet=True,
    )

    if result["success"]:
        print(result["output"])
    else:
        print(f"[error] {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


def _cmd_init(args: argparse.Namespace) -> None:
    """pyv init — scaffold a new PyV project config."""
    from scripts.scaffold_config import scaffold_config
    scaffold_config(args.lang)


def _cmd_lint(args: argparse.Namespace) -> None:
    """pyv lint — run syntax checker on a Verilog file."""
    from linter.scanner import LinterScanner
    import json

    rules_dir, ext_dirs = _resolve_grammar_dirs()

    if args.file:
        if not os.path.isfile(args.file):
            print(f"[fatal] File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            source = f.read()
    else:
        source = sys.stdin.read()

    if not source.strip():
        print("No input", file=sys.stderr)
        sys.exit(1)

    scanner = LinterScanner(rules_dir=rules_dir, ext_dirs=ext_dirs)
    diagnostics = scanner.scan(source)

    if args.json:
        data = [d.to_dict() for d in diagnostics]
        print(json.dumps(data, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        for d in diagnostics:
            start, end = d.range
            print(f"  Ln {start.line + 1}:{start.character + 1} - "
                  f"Ln {end.line + 1}:{end.character + 1}  {d.message}")

    sys.exit(1 if diagnostics else 0)


def _cmd_pipeline(args: argparse.Namespace) -> None:
    """pyv pipeline — run a single test case (dev use)."""
    from verilog.run_pipeline import main as pipeline_main
    sys.argv = [sys.argv[0]] + (args.test_name or [])
    pipeline_main()


def _cmd_new_component(args: argparse.Namespace) -> None:
    """pyv new component — scaffold a new component."""
    from scripts.scaffold_component import scaffold_component
    scaffold_component(args.name, args.lang or "verilog")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PyV Compiler — configuration-driven compiler frontend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py format input.v
  python main.py lint input.v --json
  python main.py pipeline counter
  python main.py new component my_feature --lang verilog
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # format
    p_fmt = sub.add_parser("format", help="Format a Verilog file")
    p_fmt.add_argument("file", help="Path to .v file")

    # lint
    p_lint = sub.add_parser("lint", help="Lint a Verilog file")
    p_lint.add_argument("file", nargs="?", help="Path to .v file (stdin if omitted)")
    p_lint.add_argument("--json", action="store_true", help="LSP-compatible JSON output")
    p_lint.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    # init
    p_init = sub.add_parser("init", help="Initialize a PyV project config")
    p_init.add_argument("--lang", default="verilog", help="Target language")

    # pipeline (dev)
    p_pipe = sub.add_parser("pipeline", help="Run a test case (dev)")
    p_pipe.add_argument("test_name", nargs="*", help="Test case name (e.g., counter)")

    # new
    p_new = sub.add_parser("new", help="Scaffold project artifacts")
    new_sub = p_new.add_subparsers(dest="new_type", required=True)
    p_comp = new_sub.add_parser("component", help="Scaffold a new component")
    p_comp.add_argument("name", help="Component name (snake_case)")
    p_comp.add_argument("--lang", default="verilog", help="Target language")

    args = parser.parse_args()

    dispatch = {
        "format": _cmd_format,
        "lint": _cmd_lint,
        "init": _cmd_init,
        "pipeline": _cmd_pipeline,
    }
    if args.command == "new":
        dispatch["new"] = {
            "component": _cmd_new_component,
        }[args.new_type]

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
