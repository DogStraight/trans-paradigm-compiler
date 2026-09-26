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

Doc: README.md（Quick start：CLI 子命令用法）
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

    文件缺失 → 容忍（无声明 = 全部走 `_CMD_DEFAULTS`）；TOML 损坏 → fatal
    （静默退化成"无指令声明"会让指令行为悄悄变样，同 core/config_lifecycle
    的 fail-fast；fatal 风格与 `_resolve_grammar_dirs` 一致）。
    """
    import tomllib
    from core.define import DEFAULT_RULES_DIR

    meta_path = os.path.join(_project_root, DEFAULT_RULES_DIR, "tpc.toml")
    try:
        with open(meta_path, "rb") as f:
            meta = tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        print(f"[fatal] Invalid TOML: {meta_path}: {exc}", file=sys.stderr)
        sys.exit(1)
    return meta.get("commands", {})


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


def _require_source_file(path: str) -> None:
    """源文件不存在 → fatal 退出（各指令共用）。"""
    if not os.path.isfile(path):
        print(f"[fatal] File not found: {path}", file=sys.stderr)
        sys.exit(1)


def _exit_on_pipeline_error(result: dict) -> None:
    """管线失败 → 报错退出（成功时不动）。"""
    if not result["success"]:
        print(f"[error] {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)


def _run_pipeline_for_command(
    name: str, file_path: str, *, fidelity: str = "full"
) -> dict:
    """按语言包 [commands] 声明（参数开关）跑完整管线 → result。

    语言包只声明差异项，未声明项取 `_CMD_DEFAULTS`（完整管线）。
    """
    from pipeline import run_pipeline_on_source

    cmd = _resolve_command(name)
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    return run_pipeline_on_source(
        source=source,
        input_path=file_path,
        out_dir=None,
        quiet=True,
        expand_macros=cmd.get("preprocess", True),
        analyzer_enabled=cmd.get("analyze", True),
        transform_enabled=cmd.get("transform", True),
        renderer_enabled=cmd.get("render", True),
        no_lint=not cmd.get("lint", True),
        parse_enabled=cmd.get("parse", True),
        format_output=cmd.get("plugins", {}).get("formatter", False),
        fidelity=fidelity,
    )


def _cmd_run_pipeline(name: str, args: argparse.Namespace) -> None:
    """按语言包 [commands] 指令声明（参数开关）驱动管线。"""
    _require_source_file(args.file)
    result = _run_pipeline_for_command(
        name, args.file, fidelity=getattr(args, "fidelity", None) or "full"
    )
    if not result["success"]:
        _exit_on_pipeline_error(result)
    print(result["output"])


def _cmd_format(args: argparse.Namespace) -> None:
    """tpc format — 按语言包 [commands].format 声明的参数格式化文件。"""
    _cmd_run_pipeline("format", args)


def _cmd_expand(args: argparse.Namespace) -> None:
    """tpc expand — 按语言包 [commands].expand 声明的参数展开宏并变换。"""
    _cmd_run_pipeline("expand", args)


def _trace_text_line(e: dict) -> str:
    """单元 → 一行文本摘要（impl/slot/黑板新增/产物/artifacts）。"""
    bits = []
    if e.get("impl"):
        bits.append(f"impl={e['impl']}")
    if e.get("slot"):
        bits.append(f"slot={e['slot']}")
    if e.get("extra_added"):
        bits.append("黑板+" + ",".join(e["extra_added"]))
    if e.get("produced"):
        bits.append("产物:" + ",".join(e["produced"]))
    if e.get("artifacts"):
        bits.append("artifacts:" + ",".join(e["artifacts"].keys()))
    return f"#{e.get('index')} {e.get('name')} [{e.get('kind')}] " + " ".join(bits)


def _write_trace_outputs(trace: list[dict], args: argparse.Namespace) -> bool:
    """`--html` / `--json` 落文件；返回是否落了盘（False = 走文本摘要）。"""
    if args.html:
        from pipeline.report_html import render_trace_html

        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_trace_html(trace, source_path=args.file))
        print(f"[trace] html: {args.html}")
    if args.json:
        import json

        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"trace": trace}, fh, ensure_ascii=False, indent=2)
        print(f"[trace] json: {args.json}")
    return bool(args.html or args.json)


def _cmd_trace(args: argparse.Namespace) -> None:
    """tpc trace — 时点管线执行轨迹（ADR-0015 §2 可视化产物）。

    跑完整管线（参数同 [commands].expand），取 `ctx.result["trace"]`：每单元
    一条（时点 index / kind / impl / 黑板键 / 插件自述 artifacts）。
    默认打印文本摘要；`--html`/`--json` 落文件（HTML 与 `tpc check --html`
    同一视觉语言）。
    """
    _require_source_file(args.file)
    result = _run_pipeline_for_command("expand", args.file)
    trace = result.get("trace") or []

    if not _write_trace_outputs(trace, args):
        for e in trace:
            print(_trace_text_line(e))
    _exit_on_pipeline_error(result)


def _cmd_lint(args: argparse.Namespace) -> None:
    """tpc lint — run syntax checker on a source file."""
    from linter.scanner import LinterScanner
    import json

    rules_dir, ext_dirs = _resolve_grammar_dirs()

    if args.file:
        _require_source_file(args.file)
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

    # 退出码只由**阻断类**诊断决定（语法结构错）；卫生/风格提示
    # （blocking=False，如 ST 族）列出但不计失败（与 check 的 exit 语义一致）。
    sys.exit(1 if any(d.blocking for d in diagnostics) else 0)


def _cmd_check(args: argparse.Namespace) -> None:
    """tpc check — 跨文件语义检查（分阶段：语法错误 → 语义错误）。

    单文件入口 + 递归发现被实例化模块的定义文件（同目录/--include），
    对每个文件跑 analyzer 插件（语义检查 + 跨文件联动），统一报告。
    """
    _require_source_file(args.file)

    from analyzer.checker import ProjectChecker

    rules_dir, ext_dirs = _resolve_grammar_dirs()
    checker = ProjectChecker(
        rules_dir=rules_dir,
        ext_dirs=ext_dirs,
        include_dirs=list(args.include) or None,
    )
    report = checker.check(args.file)

    # 源码内 tpc-check 豁免注释（区间形式 / disable-line 单行）
    _apply_check_suppressions(report, rules_dir)

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


def _apply_check_suppressions(report: dict, rules_dir: str) -> None:
    """应用源码内 tpc-check 豁免注释（analyzer/suppress.py），并重算 exit_code。

    豁免面向"检查通过但故意非标"的生成代码——解析失败的文件不豁免
    （parse_error 是坏文件信号，不掩盖）。豁免指令以注释形态书写，标点从
    语言包声明取（引擎不认识 `//` / `/* */`）。
    """
    from analyzer.suppress import apply_suppressions, build_suppress_map
    from lexer.comment_syntax import load_comment_syntax

    syntax = load_comment_syntax(rules_dir)
    for f in report["files"]:
        if not f.get("parse_ok", True):
            continue
        try:
            with open(f["path"], encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        smap = build_suppress_map(text, syntax)
        f["syntax"] = apply_suppressions(f["syntax"], smap)
        f["semantic"] = apply_suppressions(f["semantic"], smap)
    # 豁免后重算：任一 error 级诊断（severity 1）存在 → exit 1
    report["exit_code"] = 1 if any(
        d.get("severity") == 1
        for f in report["files"]
        for d in f["syntax"] + f["semantic"]
    ) else 0


def _print_syntax_diags(rel: str, diags: list[dict]) -> None:
    """语法阶段诊断（range 为 None 时无位置）。"""
    print(f"{rel}:")
    for d in diags:
        r = d["range"]
        if r:
            print(
                f"  [syntax] Ln {r['start']['line'] + 1}:"
                f"{r['start']['character'] + 1}  {d['message']}"
            )
        else:
            print(f"  [syntax] {d['message']}")


def _print_related(rel_info: dict) -> None:
    """关联位置补充行（`↳ 消息 at 文件:行:列`）。"""
    rl = rel_info.get("line")
    rc = rel_info.get("column")
    pos_s = (
        f" at {os.path.basename(rel_info.get('file', ''))}:{rl}:{rc}" if rl else ""
    )
    print(f"      ↳ {rel_info['message']}{pos_s}")


def _print_semantic_diags(diags: list[dict]) -> None:
    """语义阶段诊断（带 level/code 与关联位置）。"""
    for d in diags:
        r = d["range"]
        pos = (
            f"Ln {r['start']['line'] + 1}:{r['start']['character'] + 1}  " if r else ""
        )
        tag = f"[{d['level']}]" if d.get("level") else "[semantic]"
        print(f"  {tag}({d['code']}) {pos}{d['message']}")
        for rel_info in d.get("related", []):
            _print_related(rel_info)


def _print_file_diags(f: dict) -> int:
    """单文件诊断 → 文本（语法阶段在前、语义阶段在后）→ 诊断数。"""
    syntax = f["syntax"]
    semantic = f["semantic"]
    if not syntax and not semantic:
        return 0
    rel = os.path.relpath(f["path"])
    if syntax:
        _print_syntax_diags(rel, syntax)
    if semantic:
        if not syntax:
            print(f"{rel}:")
        _print_semantic_diags(semantic)
    return len(syntax) + len(semantic)


def _print_check_text(report: dict) -> None:
    """tpc check 文本输出：按文件分组，语法阶段在前、语义阶段在后。"""
    total = sum(_print_file_diags(f) for f in report["files"])
    if total == 0:
        print("No issues found.")


def _config_source_loc(src: dict) -> str:
    """配置来源的可读定位串（bare / missing / 文件列表 + section）。"""
    if src.get("bare"):
        return "<bare data>"
    if src.get("missing"):
        return f"<missing> {src.get('file', '')}"
    f = src.get("file")
    if isinstance(f, list):
        loc = f"{len(f)} files (first: {f[0]})"
    else:
        loc = f or ""
    if src.get("section"):
        loc += f" → [{src['section']}]"
    return loc


def _config_value_summary(val: object) -> str:
    """配置值摘要（容器只报形状，标量取 repr）。"""
    if isinstance(val, dict):
        return f"dict({len(val)} keys)"
    if isinstance(val, list):
        return f"list({len(val)} items)"
    return repr(val)


def _config_dump_json(loaded: dict, sources: dict) -> dict:
    """JSON 形态：{key: {source, value}}。"""
    return {
        name: {"source": sources.get(name, {}), "value": loaded[name]}
        for name in sorted(loaded)
    }


def _print_config_dump_text(loaded: dict, sources: dict, rules_dir: str) -> None:
    """文本形态的配置来源表。"""
    print(f"# Config dump — {rules_dir}")
    print(f"# {len(loaded)} keys\n")
    for name in sorted(loaded):
        print(f"{name}")
        print(f"  source: {_config_source_loc(sources.get(name, {}))}")
        print(f"  value: {_config_value_summary(loaded[name])}")
        print()


def _cmd_config_dump(args: argparse.Namespace) -> None:
    """tpc config dump — 输出配置 key 的来源（文件+section）与值摘要。

    调试工具：回答"这个配置值从哪来"。按语言包解析（resolve_with_sources，
    无全局副作用），不依赖最后一次 load_all 的状态。
    """
    from core.config_registry import ConfigRegistry
    from core.define import DEFAULT_RULES_DIR

    # 默认 rules_dir 锚定 _project_root（与 `_resolve_grammar_dirs` 同口径）：
    # DEFAULT_RULES_DIR 是**相对**路径（`grammar/verilog`），不锚定则解析结果
    # 依赖 CWD——实测 wheel 装好后从仓库外跑本指令会报
    # `ConfigError: glob 未找到匹配文件: 0*/*.toml`（根因是相对路径落到 CWD 下）。
    # `--rules-dir` 是用户显式给的路径，仍按常规相对 CWD 解析。
    rules_dir = args.rules_dir or os.path.join(_project_root, DEFAULT_RULES_DIR)
    plugins_dir = os.path.join(rules_dir, "plugins")
    loaded, sources = ConfigRegistry.resolve_with_sources(
        rules_dir, plugins_dir=plugins_dir
    )

    if args.json:
        import json

        # ensure_ascii=True：Windows GBK 控制台无法编码非 ASCII（BOM/中文），
        # 转义为 \uXXXX 保证任何终端可显示（调试工具可读性优先）。
        print(
            json.dumps(
                _config_dump_json(loaded, sources),
                ensure_ascii=True,
                indent=2 if args.pretty else None,
            )
        )
        return

    _print_config_dump_text(loaded, sources, rules_dir)


def _cmd_pipeline(args: argparse.Namespace) -> None:
    """tpc pipeline — run a single test case (dev use)."""
    from tests.e2e.run_pipeline import main as pipeline_main

    sys.argv = [sys.argv[0]] + (args.test_name or [])
    pipeline_main()


def _add_format_parser(sub) -> None:
    p_fmt = sub.add_parser("format", help="Format a source file (per [commands].format)")
    p_fmt.add_argument("file", help="Path to source file")
    p_fmt.add_argument(
        "--fidelity", default=None,
        choices=["full", "keep_blank"],
        help="Fidelity level (ADR-0006 阶段5): full=完全重排, keep_blank=保留空行",
    )


def _add_expand_parser(sub) -> None:
    p_exp = sub.add_parser(
        "expand", help="Expand macros and transform (per [commands].expand)"
    )
    p_exp.add_argument("file", help="Path to source file")


def _add_lint_parser(sub) -> None:
    p_lint = sub.add_parser("lint", help="Lint a source file")
    p_lint.add_argument("file", nargs="?", help="Path to source file (stdin if omitted)")
    p_lint.add_argument(
        "--json", action="store_true", help="LSP-compatible JSON output"
    )
    p_lint.add_argument("--pretty", action="store_true", help="Pretty-print JSON")


def _add_check_parser(sub) -> None:
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


def _add_trace_parser(sub) -> None:
    p_tr = sub.add_parser(
        "trace", help="Pipeline unit trace (analyze/transform/check) as text or HTML"
    )
    p_tr.add_argument("file", help="Path to source file")
    p_tr.add_argument(
        "--html", metavar="FILE", help="Write an HTML report to FILE"
    )
    p_tr.add_argument(
        "--json", metavar="FILE", help="Write trace JSON to FILE"
    )


def _add_pipeline_parser(sub) -> None:
    p_pipe = sub.add_parser("pipeline", help="Run a test case (dev)")
    p_pipe.add_argument("test_name", nargs="*", help="Test case name (e.g., counter)")


def _add_config_parser(sub) -> None:
    p_cfg = sub.add_parser("config", help="Config introspection")
    cfg_sub = p_cfg.add_subparsers(dest="config_type", required=True)
    p_dump = cfg_sub.add_parser("dump", help="Dump config keys with sources")
    p_dump.add_argument("--rules-dir", default=None, help="Language pack dir")
    p_dump.add_argument("--json", action="store_true", help="JSON output")
    p_dump.add_argument("--pretty", action="store_true", help="Pretty-print JSON")


# 子命令 → 注册函数（与 _dispatch 的映射同名同序）
_SUBCOMMAND_PARSERS = (
    ("format", _add_format_parser),
    ("expand", _add_expand_parser),
    ("lint", _add_lint_parser),
    ("check", _add_check_parser),
    ("trace", _add_trace_parser),
    ("pipeline", _add_pipeline_parser),
    ("config", _add_config_parser),
)


def _register_subparsers(sub, allow=None) -> None:
    """注册子命令（可裁剪）。

    allow: 允许的命令名集合（None = 全部）。打包管线（packaging/build_pipeline.py
    生成的切面入口）用它只挂载需要的命令；main() 注册全部。
    """
    for name, add_parser in _SUBCOMMAND_PARSERS:
        if allow is None or name in allow:
            add_parser(sub)


def _dispatch(args) -> None:
    """按解析结果分发到命令处理函数（与 _register_subparsers 配套）。"""
    dispatch = {
        "format": _cmd_format,
        "expand": _cmd_expand,
        "trace": _cmd_trace,
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
