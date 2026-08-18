#!/usr/bin/env python3
"""
TransParadigm Compiler Pipeline - End-to-end compilation with stage control.

管线核心（run_pipeline_on_source / format_generated / _load_pipeline_defaults /
_PIPELINE_SHARED）已移入正式包 `pipeline/`（2026-08-18 开源就绪：CLI 与测试共用，
wheel 安装后 CLI 可用）。本文件保留测试 CLI（find_test_file / parse_args / main），
从 pipeline 导入核心，并保留测试环境特定代码（sys.path 插入 / stdout 重定向）。
"""

import sys
import os
import argparse

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Force stdout to UTF-8
sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)

# 管线核心（正式包）
from pipeline import (  # noqa: E402
    run_pipeline_on_source,
    format_generated,
    _load_pipeline_defaults,
    _PIPELINE_SHARED,
)
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS  # noqa: E402


# ── Helpers ──
def find_test_file(test_name: str, hint: str = "") -> tuple[str, str, str]:
    """Find test file in tests/ directory. Returns (full_path, group, stem)."""
    src_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = os.path.join(src_dir, "samples")
    groups = [hint] if hint else ["normal", "errors"]
    stem = test_name.replace("ref_", "").replace(".v", "")
    for group in groups:
        d = os.path.join(tests_dir, group, "ref")
        f = os.path.join(d, f"ref_{stem}.v")
        if os.path.exists(f):
            return f, group, stem
    return "", "", ""


# ── Command-line entry ──
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TransParadigm Compiler Pipeline – stage control and flexible execution",
        epilog="Example: python run_pipeline.py ref_counter --no-analyzer --stage=parse",
    )
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument(
        "test_name",
        nargs="?",
        default=None,
        help="Test case name (e.g., 'counter' or 'ref_counter'), auto-located in tests/",
    )
    input_group.add_argument(
        "-i", "--input", type=str, help="Direct Verilog source file path"
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory (auto-detected if not given)",
    )

    parser.add_argument(
        "--stage",
        choices=["lex", "parse", "analyze", "transform", "render"],
        help="Stop after specified stage (for debugging)",
    )
    parser.add_argument(
        "--no-analyzer",
        dest="analyzer",
        action="store_false",
        help="Skip semantic analysis",
    )
    parser.add_argument(
        "--no-transform",
        dest="transform",
        action="store_false",
        help="Skip AST transform",
    )
    parser.add_argument(
        "--no-renderer",
        dest="renderer",
        action="store_false",
        help="Skip code generation",
    )

    parser.add_argument(
        "--no-lint",
        action="store_true",
        help="Skip linter pre-check",
    )
    parser.add_argument(
        "--expand-macros", action="store_true", help="Expand `define macros"
    )
    parser.add_argument(
        "--inline-comments",
        action="store_true",
        help="Re-inject inline comment fingerprints",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress log output and skip JSON/symbol file saves",
    )
    parser.add_argument(
        "--no-semantic",
        action="store_true",
        help="Skip semantic analysis (analyzer + transform)",
    )

    parser.add_argument(
        "--rules-dir",
        type=str,
        default=DEFAULT_RULES_DIR,
        help="Core grammar rules directory",
    )
    parser.add_argument(
        "--ext-dirs",
        type=str,
        nargs="*",
        default=DEFAULT_EXT_DIRS,
        help="Extended grammar rules directories (can specify multiple)",
    )

    parser.add_argument(
        "--include",
        type=str,
        action="append",
        dest="include_dirs",
        default=None,
        help="Add directory to preprocessor include search path (can specify multiple)",
    )
    parser.add_argument(
        "-D", "--define",
        action="append",
        dest="define",
        default=None,
        help="Predefine a macro for conditional compilation: -D NAME or -D NAME=VAL (can repeat)",
    )
    parser.add_argument(
        "-U", "--undefine",
        action="append",
        dest="undefine",
        default=None,
        help="Force a macro to be undefined for conditional compilation: -U NAME (can repeat)",
    )

    parser.set_defaults(analyzer=True, transform=True, renderer=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determine source file
    src_file = args.input
    if not src_file:
        src_file, _, _ = find_test_file(args.test_name or "led_blinker")
        if not src_file:
            print(f"[error] test file not found: {args.test_name}", file=sys.stderr)
            sys.exit(1)

    # -D NAME[=VAL] → predefined；-U NAME → undefine
    predefined: dict[str, str] = {}
    for d in args.define or []:
        if "=" in d:
            k, v = d.split("=", 1)
            predefined[k] = v
        else:
            predefined[d] = "1"
    undefine: set[str] = set(args.undefine or [])
    with open(src_file, "r", encoding="utf-8") as f:
        source = f.read()

    result = run_pipeline_on_source(
        source=source,
        input_path=src_file,
        out_dir=args.out_dir,
        expand_macros=args.expand_macros,
        inline_comments=args.inline_comments,
        quiet=args.quiet,
        analyzer_enabled=args.analyzer and not args.no_semantic,
        transform_enabled=args.transform and not args.no_semantic,
        renderer_enabled=args.renderer,
        stage=args.stage,
        no_lint=args.no_lint,
        rules_dir=args.rules_dir,
        ext_dirs=args.ext_dirs,
        include_dirs=args.include_dirs,
        predefined=predefined,
        undefine=undefine,
    )

    if not result["success"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
