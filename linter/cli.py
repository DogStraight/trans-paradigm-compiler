"""
cli.py — tpc-lint 命令行入口

用法:
    python linter/cli.py input.v                          # 文本输出
    python linter/cli.py input.v --json                   # LSP 兼容 JSON
    python linter/cli.py input.v --json --pretty           # 格式化 JSON
    echo "module m; wire a; endmodule" | python linter/cli.py   # 从 stdin
Doc: docs/linter_architecture.md（tpc lint 命令）
"""

import sys
import os
import json
import argparse
import io

# 强制 UTF-8 输出（避免中文乱码）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS
from linter.scanner import LinterScanner


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="TransParadigm Linter — 语法错误扫描器")
    parser.add_argument("input", nargs="?", help="源文件路径（省略则从 stdin 读取）")
    parser.add_argument(
        "--json", action="store_true", help="以 LSP Diagnostic JSON 格式输出"
    )
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    # 读取源码
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            source = f.read()
    else:
        source = sys.stdin.read()

    if not source.strip():
        print("No input", file=sys.stderr)
        sys.exit(1)

    # 确定语法规则目录
    rules_dir = os.path.join(
        os.path.dirname(__file__), "..", DEFAULT_RULES_DIR
    )
    ext_dirs = []
    for ed in DEFAULT_EXT_DIRS:
        candidate = os.path.join(os.path.dirname(__file__), "..", ed)
        if os.path.isdir(candidate):
            ext_dirs.append(candidate)

    if not os.path.isdir(rules_dir):
        print(f"错误：找不到语法规则目录 {rules_dir}", file=sys.stderr)
        sys.exit(1)

    # 扫描
    scanner = LinterScanner(
        rules_dir=rules_dir,
        ext_dirs=ext_dirs,
    )
    diagnostics = scanner.scan(source)

    if args.json:
        from linter import lsp_diagnostic
        data = [lsp_diagnostic(d) for d in diagnostics]
        indent = 2 if args.pretty else None
        print(json.dumps(data, ensure_ascii=False, indent=indent))
    else:
        for d in diagnostics:
            start = d.range[0]
            end = d.range[1]
            print(
                f"  Ln {start.line + 1}:{start.character + 1} - "
                f"Ln {end.line + 1}:{end.character + 1}  {d.message}"
            )

    sys.exit(1 if diagnostics else 0)


if __name__ == "__main__":
    cli_main()
