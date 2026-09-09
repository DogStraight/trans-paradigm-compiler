#!/usr/bin/env python3
"""
main.py — TransParadigm Compiler CLI entry point

Usage (installed as `tpc`):
    tpc format <file>                  Format a source file
    tpc lint <file> [--json]           Lint a source file (syntax only)
    tpc check <file> [--include DIR]   Cross-file semantic check (syntax then semantic)
    tpc pipeline [test_name]           Run a single test
    tpc config dump                    Show config key sources
    tpc --version                      Show version
"""

import sys
import os
import argparse

from core import __version__

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _load_commands() -> dict:
    """从语言包 tpc.toml 读 [commands] 段（指令 → 管线阶段定义）。

    指令在语言包声明（如 format = { stages = [...], expand_macros = ... }），
    main.py 按声明驱动 run_pipeline_on_source（stages 参数跳过未声明阶段）。
    """
    import tomllib
    from core.define import DEFAULT_RULES_DIR

    meta_path = os.path.join(_project_root, DEFAULT_RULES_DIR, "tpc.toml")
    try:
        with open(meta_path, "rb") as f:
            meta = tomllib.load(f)
        return meta.get("commands", {})
    except Exception:
        return {}


# 指令默认值 = 完整管线（preprocess/lint/parse/analyze/transform/render 全 true，
# plugins.formatter=false）。语言包 [commands] 只声明**差异项**。
_CMD_DEFAULTS: dict = {
    "preprocess": True,
    "lint": True,
    "parse": True,
    "analyze": True,
    "transform": True,
    "render": True,
    "plugins": {"formatter": False},
}


def _resolve_command(name: str) -> dict:
    """指令合并默认值：语言包只声明差异项，未声明项取完整管线默认。"""
    cmd = {k: v for k, v in _CMD_DEFAULTS.items() if k != "plugins"}
    plugins = dict(_CMD_DEFAULTS["plugins"])
    raw = _load_commands().get(name, {})
    plugins.update(raw.get("plugins", {}))
    cmd.update({k: v for k, v in raw.items() if k != "plugins"})
    cmd["plugins"] = plugins
    return cmd


def _resolve_grammar_dirs() -> tuple[str, list[str]]:
    """Resolve and validate grammar directories from tpc.toml metadata."""
    from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS

    root = _project_root
    rules_dir = os.path.join(root, DEFAULT_RULES_DIR)
    if not os.path.isdir(rules_dir):
        print(f"[fatal] Grammar directory not found: {rules_dir}", file=sys.stderr)
        print(f"        Check grammar/tpc.toml [grammar].rules_dir", file=sys.stderr)
        sys.exit(1)

    ext_dirs = []
    for ed in DEFAULT_EXT_DIRS:
        candidate = os.path.join(root, ed)
        if os.path.isdir(candidate):
            ext_dirs.append(candidate)
        else:
            print(
                f"[warn] EXT grammar directory not found: {candidate}", file=sys.stderr
            )

    return rules_dir, ext_dirs


def _cmd_run_pipeline(name: str, args: argparse.Namespace) -> None:
    """按语言包 [commands] 指令声明（参数开关）驱动管线。"""
    if not os.path.isfile(args.file):
        print(f"[fatal] File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    from pipeline import run_pipeline_on_source

    cmd = _resolve_command(name)

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    result = run_pipeline_on_source(
        source=source,
        input_path=args.file,
        out_dir=None,
        quiet=True,
        expand_macros=cmd.get("preprocess", True),
        analyzer_enabled=cmd.get("analyze", True),
        transform_enabled=cmd.get("transform", True),
        renderer_enabled=cmd.get("render", True),
        no_lint=not cmd.get("lint", True),
        parse_enabled=cmd.get("parse", True),
        format_output=cmd.get("plugins", {}).get("formatter", False),
        fidelity=getattr(args, "fidelity", None) or "full",
    )

    if result["success"]:
        print(result["output"])
    else:
        print(f"[error] {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


def _cmd_format(args: argparse.Namespace) -> None:
    """tpc format — 按语言包 [commands].format 声明的参数格式化文件。"""
    _cmd_run_pipeline("format", args)


def _cmd_expand(args: argparse.Namespace) -> None:
    """tpc expand — 按语言包 [commands].expand 声明的参数展开宏并变换。"""
    _cmd_run_pipeline("expand", args)


def _cmd_lint(args: argparse.Namespace) -> None:
    """tpc lint — run syntax checker on a source file."""
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
        from linter import lsp_diagnostic
        data = [lsp_diagnostic(d) for d in diagnostics]
        print(json.dumps(data, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        for d in diagnostics:
            start, end = d.range
            print(
                f"  Ln {start.line + 1}:{start.character + 1} - "
                f"Ln {end.line + 1}:{end.character + 1}  {d.message}"
            )

    sys.exit(1 if diagnostics else 0)


def _cmd_check(args: argparse.Namespace) -> None:
    """tpc check — 跨文件语义检查（分阶段：语法错误 → 语义错误）。

    单文件入口 + 递归发现被实例化模块的定义文件（同目录/--include），
    对每个文件跑 analyzer 插件（语义检查 + 跨文件联动），统一报告。
    """
    if not os.path.isfile(args.file):
        print(f"[fatal] File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    from analyzer.checker import ProjectChecker

    rules_dir, ext_dirs = _resolve_grammar_dirs()
    checker = ProjectChecker(
        rules_dir=rules_dir,
        ext_dirs=ext_dirs,
        include_dirs=list(args.include) or None,
    )
    report = checker.check(args.file)

    # 源码内 tpc-check 豁免注释（/* tpc-check off */ 区间 / disable-line 单行）
    _apply_check_suppressions(report)

    if args.html:
        from analyzer.report_html import render_html_report

        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html_report(report))
    elif args.json:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        _print_check_text(report)
    sys.exit(report["exit_code"])


def _apply_check_suppressions(report: dict) -> None:
    """应用源码内 tpc-check 豁免注释（analyzer/suppress.py），并重算 exit_code。

    豁免面向"检查通过但故意非标"的生成代码——解析失败的文件不豁免
    （parse_error 是坏文件信号，不掩盖）。
    """
    from analyzer.suppress import apply_suppressions, build_suppress_map

    for f in report["files"]:
        if not f.get("parse_ok", True):
            continue
        try:
            with open(f["path"], encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        smap = build_suppress_map(text)
        f["syntax"] = apply_suppressions(f["syntax"], smap)
        f["semantic"] = apply_suppressions(f["semantic"], smap)
    # 豁免后重算：任一 error 级诊断（severity 1）存在 → exit 1
    report["exit_code"] = 1 if any(
        d.get("severity") == 1
        for f in report["files"]
        for d in f["syntax"] + f["semantic"]
    ) else 0


def _print_check_text(report: dict) -> None:
    """tpc check 文本输出：按文件分组，语法阶段在前、语义阶段在后。"""
    total = 0
    for f in report["files"]:
        syntax = f["syntax"]
        semantic = f["semantic"]
        if not syntax and not semantic:
            continue
        total += len(syntax) + len(semantic)
        rel = os.path.relpath(f["path"])
        if syntax:
            print(f"{rel}:")
            for d in syntax:
                r = d["range"]
                if r:
                    print(
                        f"  [syntax] Ln {r['start']['line'] + 1}:"
                        f"{r['start']['character'] + 1}  {d['message']}"
                    )
                else:
                    print(f"  [syntax] {d['message']}")
        if semantic:
            if not syntax:
                print(f"{rel}:")
            for d in semantic:
                r = d["range"]
                pos = (
                    f"Ln {r['start']['line'] + 1}:{r['start']['character'] + 1}  "
                    if r
                    else ""
                )
                tag = f"[{d['level']}]" if d.get("level") else "[semantic]"
                print(f"  {tag}({d['code']}) {pos}{d['message']}")
                for rel_info in d.get("related", []):
                    rl = rel_info.get("line")
                    rc = rel_info.get("column")
                    pos_s = (
                        f" at {os.path.basename(rel_info.get('file', ''))}"
                        f":{rl}:{rc}"
                        if rl
                        else ""
                    )
                    print(f"      ↳ {rel_info['message']}{pos_s}")
    if total == 0:
        print("No issues found.")


def _cmd_config_dump(args: argparse.Namespace) -> None:
    """tpc config dump — 输出配置 key 的来源（文件+section）与值摘要。

    调试工具：回答"这个配置值从哪来"。按语言包解析（resolve_with_sources，
    无全局副作用），不依赖最后一次 load_all 的状态。
    """
    from core.config_registry import ConfigRegistry
    from core.define import DEFAULT_RULES_DIR

    rules_dir = args.rules_dir or DEFAULT_RULES_DIR
    plugins_dir = os.path.join(rules_dir, "plugins")
    loaded, sources = ConfigRegistry.resolve_with_sources(
        rules_dir, plugins_dir=plugins_dir
    )

    if args.json:
        import json

        out = {}
        for name in sorted(loaded):
            src = sources.get(name, {})
            out[name] = {
                "source": src,
                "value": loaded[name],
            }
        # ensure_ascii=True：Windows GBK 控制台无法编码非 ASCII（BOM/中文），
        # 转义为 \uXXXX 保证任何终端可显示（调试工具可读性优先）。
        print(json.dumps(out, ensure_ascii=True, indent=2 if args.pretty else None))
        return

    print(f"# Config dump — {rules_dir}")
    print(f"# {len(loaded)} keys\n")
    for name in sorted(loaded):
        src = sources.get(name, {})
        if src.get("bare"):
            loc = "<bare data>"
        elif src.get("missing"):
            loc = f"<missing> {src.get('file', '')}"
        else:
            f = src.get("file")
            if isinstance(f, list):
                loc = f"{len(f)} files (first: {f[0]})"
            else:
                loc = f or ""
            if src.get("section"):
                loc += f" → [{src['section']}]"
        print(f"{name}")
        print(f"  source: {loc}")
        val = loaded[name]
        if isinstance(val, dict):
            print(f"  value: dict({len(val)} keys)")
        elif isinstance(val, list):
            print(f"  value: list({len(val)} items)")
        else:
            print(f"  value: {val!r}")
        print()


def _cmd_pipeline(args: argparse.Namespace) -> None:
    """tpc pipeline — run a single test case (dev use)."""
    from tests.e2e.run_pipeline import main as pipeline_main

    sys.argv = [sys.argv[0]] + (args.test_name or [])
    pipeline_main()


def _register_subparsers(sub, allow=None) -> None:
    """注册子命令（可裁剪）。

    allow: 允许的命令名集合（None = 全部）。打包管线（packaging/build_pipeline.py
    生成的切面入口）用它只挂载需要的命令；main() 注册全部。
    """

    def want(name: str) -> bool:
        return allow is None or name in allow

    if want("format"):
        p_fmt = sub.add_parser("format", help="Format a source file (per [commands].format)")
        p_fmt.add_argument("file", help="Path to source file")
        p_fmt.add_argument(
            "--fidelity", default=None,
            choices=["full", "keep_blank"],
            help="Fidelity level (ADR-0006 阶段5): full=完全重排, keep_blank=保留空行",
        )

    if want("expand"):
        p_exp = sub.add_parser(
            "expand", help="Expand macros and transform (per [commands].expand)"
        )
        p_exp.add_argument("file", help="Path to source file")

    if want("lint"):
        p_lint = sub.add_parser("lint", help="Lint a source file")
        p_lint.add_argument("file", nargs="?", help="Path to source file (stdin if omitted)")
        p_lint.add_argument(
            "--json", action="store_true", help="LSP-compatible JSON output"
        )
        p_lint.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    if want("check"):
        p_check = sub.add_parser(
            "check", help="Cross-file semantic check (syntax then semantic stages)"
        )
        p_check.add_argument("file", help="Path to source file")
        p_check.add_argument(
            "--include",
            action="append",
            default=[],
            help="Extra directory to search for module definitions (repeatable)",
        )
        p_check.add_argument(
            "--json", action="store_true", help="LSP-compatible JSON output"
        )
        p_check.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
        p_check.add_argument(
            "--html", metavar="FILE", help="Write an HTML report to FILE"
        )

    if want("pipeline"):
        p_pipe = sub.add_parser("pipeline", help="Run a test case (dev)")
        p_pipe.add_argument("test_name", nargs="*", help="Test case name (e.g., counter)")

    if want("config"):
        p_cfg = sub.add_parser("config", help="Config introspection")
        cfg_sub = p_cfg.add_subparsers(dest="config_type", required=True)
        p_dump = cfg_sub.add_parser("dump", help="Dump config keys with sources")
        p_dump.add_argument("--rules-dir", default=None, help="Language pack dir")
        p_dump.add_argument("--json", action="store_true", help="JSON output")
        p_dump.add_argument("--pretty", action="store_true", help="Pretty-print JSON")


def _dispatch(args) -> None:
    """按解析结果分发到命令处理函数（与 _register_subparsers 配套）。"""
    dispatch = {
        "format": _cmd_format,
        "expand": _cmd_expand,
        "lint": _cmd_lint,
        "check": _cmd_check,
        "pipeline": _cmd_pipeline,
    }
    if args.command == "config":
        dispatch["config"] = {
            "dump": _cmd_config_dump,
        }[args.config_type]

    dispatch[args.command](args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TransParadigm Compiler — configuration-driven compiler frontend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tpc format input.v
  tpc lint input.v --json
  tpc pipeline counter
  tpc config dump
        """,
    )
    # 顶层 --version：与 subcommand 共存（argparse version action，打印后 exit 0）
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version and exit",
    )
    _register_subparsers(parser.add_subparsers(dest="command", required=True))

    args = parser.parse_args()
    _dispatch(args)


if __name__ == "__main__":
    main()
