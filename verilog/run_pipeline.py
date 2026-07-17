#!/usr/bin/env python3
"""
PyV Compiler Pipeline - End-to-end compilation with stage control.
Supports direct input, test discovery, macro expansion, inline comments,
and optional semantic/transform/render stages.
"""

import sys
import os
import argparse
from datetime import datetime
from typing import Any
from core.define import Node

# ── 预加载组件（确保组件插件先于引擎插件注册）──
from core.component_loader import load_all_components

load_all_components()
# 显式导入引擎插件，确保在组件插件之后注册
import transform.config_driven  # noqa: F401, E402

# ── 词法 / 语法 / 配置 ──
from lexer import Lexer, pre_scan, load_pre_scan_config
from parser import Parser, setup_grammar
from core.define import (
    ParseError,
    GrammarRulesRegister,
    DEFAULT_RULES_DIR,
    DEFAULT_EXT_DIRS,
)
from core.config_registry import ConfigRegistry
from core.utils import ensure_dir, save_json
from parser.rule_selector import RuleSelector

# ── 分析器 ──
from analyzer import AnalysisTraversal

# ── 语言配置（组件系统收集）──
from core.component_loader import get_component_mapping_config
from grammar.verilog.ext._components.typed_ports._mapping import collect_callbacks

# ── 变换器 ──
from transform import AstTransformer, collect_extra_asts
from normalizer import normalize_ast

# ── 渲染器 ──
from renderer.renderer import Renderer
from renderer.inline_comment import restore_comments, restore_line_comments

# ── Linter（前置语法检查）──
from linter.scanner import LinterScanner

# ── 预处理器（可选）──
from preprocessor import (
    scan_directives,
    expand_tokens,
    protect_and_reverse,
    load_macro_config,
)

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 模块级共享状态：rules/lexer/renderer/transformer 按 rules_dir 缓存，避免重复初始化
_PIPELINE_SHARED: dict = {}

from scripts.ast_debug import (
    enable_ast_debug,
    dump_ast_compact,
    dump_tokens,
    count_ast_nodes,
)

# Force stdout to UTF-8
sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)


# ---------------------------- Helpers ----------------------------
def find_test_file(test_name: str, hint: str = "") -> tuple[str, str, str]:
    """Find test file in tests/ directory. Returns (full_path, group, stem)."""
    src_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = os.path.join(src_dir, "tests")
    groups = [hint] if hint else ["normal", "errors"]
    stem = test_name.replace("ref_", "").replace(".v", "")
    for group in groups:
        d = os.path.join(tests_dir, group, "ref")
        f = os.path.join(d, f"ref_{stem}.v")
        if os.path.exists(f):
            return f, group, stem
    return "", "", ""


# ---------------------------- Core Pipeline ----------------------------
def run_pipeline_on_source(
    source: str,
    input_path: str | None = None,
    out_dir: str | None = None,
    expand_macros: bool = False,
    inline_comments: bool = False,
    debug: bool = False,
    quiet: bool = False,
    analyzer_enabled: bool = True,
    transform_enabled: bool = True,
    renderer_enabled: bool = True,
    stage: str | None = None,
    no_lint: bool = False,
    rules_dir: str = DEFAULT_RULES_DIR,
    ext_dirs: list[str] | None = DEFAULT_EXT_DIRS,
    include_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """
    Core pipeline: process Verilog source and return results.

    Returns dict:
        success: bool
        output: str (generated Verilog code, if renderer enabled)
        ast: Any (final AST)
        error: str (error message if any)
        parser: Parser instance (for comment table, etc.)
    """

    # Quiet-aware logger
    def _log(msg: str, *args, **kwargs) -> None:
        if not quiet:
            print(msg, *args, **kwargs)

    result = {
        "success": False,
        "output": "",
        "ast": None,
        "extra_asts": [],
        "error": "",
        "parser": None,
    }

    if debug:
        enable_ast_debug(True)
        _log("[debug] enabled")

    original_source = source

    # Determine output directory
    if out_dir is None:
        if input_path and "tests" in input_path:
            parts = input_path.replace("\\", "/").split("/")
            group = (
                "normal"
                if "normal" in parts
                else ("errors" if "errors" in parts else "normal")
            )
            tests_dir = os.path.join(os.path.dirname(__file__), "tests")
            out_dir = os.path.join(tests_dir, group)
        else:
            out_dir = None  # 无合法输出目录，跳过文件写入
    if out_dir:
        gen_dir = os.path.join(out_dir, "gen")
        ast_dir = os.path.join(out_dir, "ast")
        sym_dir = os.path.join(out_dir, "symbols")
        lex_dir = os.path.join(out_dir, "lex")
        ensure_dir(gen_dir)
        ensure_dir(ast_dir)
        ensure_dir(sym_dir)
        ensure_dir(lex_dir)
        cb_dir = os.path.join(out_dir, "trans_callback")
        ensure_dir(cb_dir)
    else:
        gen_dir = ast_dir = sym_dir = lex_dir = cb_dir = None

    # Base filename for intermediate files
    if input_path:
        stem = os.path.splitext(os.path.basename(input_path))[0]
        base_name = stem.replace("ref_", "")
    else:
        base_name = "input"

    gen_file = os.path.join(gen_dir, f"gen_{base_name}.v") if gen_dir else None
    ast_json = os.path.join(ast_dir, f"{base_name}.json") if ast_dir else None
    sym_json = os.path.join(sym_dir, f"{base_name}.json") if sym_dir else None
    cb_json = os.path.join(cb_dir, f"{base_name}.json") if cb_dir else None

    # ---- Stage: 配置加载（只执行一次，缓存后跳过）----
    if "_config_loaded" not in _PIPELINE_SHARED:
        ConfigRegistry.load_all(rules_dir, ext_dirs=ext_dirs)
        _PIPELINE_SHARED["_config_loaded"] = True

    # ---- Stage: 宏指令扫描（仅提取宏表，不展开字符串）----
    macro_table = {}
    directive_lines = []
    restore_stack = None
    if expand_macros:
        macro_table, directive_lines, source = scan_directives(
            source, rules_dir, source_path=input_path, search_dirs=include_dirs
        )
        _log(f"[preprocessor] macros defined: {len(macro_table)}")

    # ---- Stage: Shared pipeline context (rules, lexer, renderer, etc.) ----
    # 所有按 rules_dir 可复用的组件集中初始化并缓存
    ctx = _PIPELINE_SHARED
    if rules_dir not in ctx:

        # 语法规则（含 EXT 注入）
        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ext_dirs
        )
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rule_selector = RuleSelector(rules, stmt_names)
        lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_dirs)
        linter = LinterScanner(rules_dir=rules_dir, ext_dirs=ext_dirs)
        renderer = Renderer(rules_dir=rules_dir)
        ctx[rules_dir] = {
            "rules": rules,
            "rule_selector": rule_selector,
            "lexer": lexer,
            "linter": linter,
            "renderer": renderer,
        }
    shared = ctx[rules_dir]
    rules = shared["rules"]
    rule_selector = shared["rule_selector"]
    lexer = shared["lexer"]
    linter = shared["linter"]
    renderer = shared["renderer"]

    # ---- Stage: Lexical analysis ----
    tokens = lexer.tokenize(source)
    if not quiet and lex_dir:
        tok_path = os.path.join(lex_dir, f"tokens_{base_name}.txt")
        with open(tok_path, "w", encoding="utf-8") as f:
            for tok in tokens:
                f.write(f"{tok.column},{tok.line}:{tok.type} {tok.content}\n")
    _log(f"[lexer] tokens: {len(tokens)}")
    if stage == "lex":
        result["success"] = True
        return result

    # ---- Stage: 纯文本宏展开（在 lexer 之前）----
    if expand_macros and macro_table:
        source, restore_stack = expand_tokens(source, macro_table)
        tokens = lexer.tokenize(source)
        _log(f"[preprocessor] macros expanded, tokens: {len(tokens)}")

    # ---- Stage: Pre-scan ----
    pre_scan_config = load_pre_scan_config(rules_dir)
    pre_symbols = pre_scan(source, pre_scan_config)
    if pre_symbols:
        _log(f"[prescan] symbols: {len(pre_symbols)}")

    # ---- Stage: Lint（前置语法检查，失败时截断管线）----
    if not no_lint:
        lint_errors = linter.scan(source)
        if lint_errors:
            for err in lint_errors:
                _log(
                    f"[linter] {err.message} at L{err.range[0].line}:{err.range[0].character}"
                )
            result["error"] = f"lint failed: {len(lint_errors)} error(s)"
            return result

    # ---- Stage: Parse ----
    # Instantiate Parser with injected rules and rule_selector
    parser = Parser(
        rules_dir=rules_dir,
        pre_symbols=pre_symbols,
        rules=rules,
        rule_selector=rule_selector,
    )
    parser.pre_hints = pre_scan_config.get("hints", {})

    # No longer need to manually assign parser.grammar_rules,
    # statement_rule_names, rule_selector, or atomic_rules — all are set internally.

    try:
        ast = parser.parse(tokens)
    except ParseError as e:
        result["error"] = str(e)
        print(f"\n[parser] Parse failed:\n{e}", file=sys.stderr)
        return result
    if ast is None:
        result["error"] = "parser returned None"
        _log("[parser] parse failed")
        return result
    result["parser"] = parser
    if stage == "parse":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: AST normalization ----
    ast = normalize_ast(ast)
    if debug:
        print(f"[ast] nodes (normalized): {count_ast_nodes(ast)}")
        print("[ast] structure:")
        dump_ast_compact(ast)
        print()
        if len(tokens) <= 150:
            print("[lexer] token stream:")
            dump_tokens(tokens)

    if not quiet and ast_json:
        save_json(ast.dump(), ast_json, "ast", log_fn=_log)

    # ---- Stage: Semantic analysis ----
    analyzer = None
    if analyzer_enabled:
        analyzer = AnalysisTraversal(rules)
        ast = analyzer.analyze(ast)
        if analyzer.root_scope is None:
            _log("[analyzer] warning: no scope produced")
        else:
            if not quiet:
                if sym_json:
                    save_json(
                        analyzer.root_scope.to_dict(), sym_json, "symbols", log_fn=_log
                    )
                # Dump transform callbacks (_ref_callbacks) to trans_callback/
                callbacks = collect_callbacks(analyzer.root_scope)
                if callbacks and cb_json:
                    save_json(callbacks, cb_json, "callbacks", log_fn=_log)
            _log(f"[symbols] {len(analyzer.all_symbols)} symbols")
        if analyzer.has_errors:
            for d in analyzer.diagnostics:
                _log(f"[analyzer] {d}")
            if any(d.level == "error" for d in analyzer.diagnostics):
                result["error"] = "; ".join(
                    str(d) for d in analyzer.diagnostics if d.level == "error"
                )
                _log("[analyzer] semantic errors, stopping pipeline")
                return result
        scope = analyzer.root_scope
    else:
        _log("[analyzer] skipped")
        scope = None
    if stage == "analyze":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: AST transform ----
    if transform_enabled and analyzer is not None and scope is not None:
        # 通过共享上下文传递规则和映射配置，插件自动从注册表实例化
        mp_entries, rv_entries = get_component_mapping_config()
        mapping_cfg: dict = {}
        mapping_cfg.update(mp_entries)
        mapping_cfg.update(rv_entries)
        AstTransformer.set_shared("rules", rules)
        AstTransformer.set_shared("mapping_cfg", mapping_cfg)
        transformer = AstTransformer()

        # 一次 transform 完成：映射表构建 + 配置变换
        ast = transformer.transform(ast, scope)

        # 收集变换统计
        parts = []
        for plugin in transformer.plugins:
            if hasattr(plugin, "stats"):
                s = plugin.stats
                for k, v in s.items():
                    if v:
                        parts.append(f"{k}={v}")
        if parts:
            _log(f"[transform] {' '.join(parts)}")
    elif transform_enabled:
        _log("[transform] skipped (analyzer=None or no scope)")
    if stage == "transform":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: 收集虚拟逻辑分发（TransformPlugin 已将提取结果存入共享上下文）----
    extra_asts: list[tuple[str, Node]] = collect_extra_asts()
    if extra_asts:
        _log(f"[remapper] extracted {len(extra_asts)} extra AST(s)")

    # ---- Stage: Render ----
    if renderer_enabled:
        content = renderer.render(ast)

        # Reverse macro protection
        if macro_table:
            macro_raw = load_macro_config()
            define_kw = macro_raw.get("directives", {}).get("define", "define")
            content = protect_and_reverse(
                content,
                original_source,
                macro_table,
                define_keyword=define_kw,
                lexer=lexer,
                restoration_stack=restore_stack,
            )
            _log("[preprocessor] macros reversed")

        # Restore directive lines
        if directive_lines:
            content = "\n".join(directive_lines) + "\n" + content
            _log(f"[preprocessor] directives restored: {len(directive_lines)}")

        # Inline comment restoration（锚点匹配，宏展开后亦可用）
        if inline_comments:
            anchors = getattr(parser, "_comment_anchors", None)
            if anchors:
                content, n = restore_comments(content, anchors)
                _log(f"[comments] inline anchor restoration: {n} items")

        # Line comment restoration（列表结构内被 production skip 吞掉的注释，渲染后回插）
        line_anchors = getattr(parser, "_line_comment_anchors", None)
        if line_anchors:
            content, n = restore_line_comments(content, line_anchors)
            _log(f"[comments] line anchor restoration: {n} items")

        # Write output
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"// Generated by PyV Compiler at {stamp}\n\n"
        if gen_file:
            with open(gen_file, "w", encoding="utf-8") as f:
                f.write(header + content)
            _log(f"[output] {gen_file}")

        # Render extra ASTs as separate files
        for out_name, extra_root in extra_asts:
            if gen_dir:
                extra_content = renderer.render(extra_root)
                extra_file = os.path.join(gen_dir, f"gen_{out_name}.v")
                with open(extra_file, "w", encoding="utf-8") as f:
                    f.write(header + extra_content)
                _log(f"[remapper] extra output: {extra_file}")

        result["output"] = content
        result["ast"] = ast
        result["success"] = True
    else:
        print("[renderer] skipped")
        result["ast"] = ast

    return result


# ---------------------------- Command-line entry ----------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PyV Compiler Pipeline – stage control and flexible execution",
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
        "--debug",
        action="store_true",
        help="Print debug info (AST structure, token stream)",
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

    with open(src_file, "r", encoding="utf-8") as f:
        source = f.read()

    result = run_pipeline_on_source(
        source=source,
        input_path=src_file,
        out_dir=args.out_dir,
        expand_macros=args.expand_macros,
        inline_comments=args.inline_comments,
        debug=args.debug,
        quiet=args.quiet,
        analyzer_enabled=args.analyzer and not args.no_semantic,
        transform_enabled=args.transform and not args.no_semantic,
        renderer_enabled=args.renderer,
        stage=args.stage,
        no_lint=args.no_lint,
        rules_dir=args.rules_dir,
        ext_dirs=args.ext_dirs,
        include_dirs=args.include_dirs,
    )

    if not result["success"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
