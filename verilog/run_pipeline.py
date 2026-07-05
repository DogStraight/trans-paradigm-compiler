#!/usr/bin/env python3
"""
PyV Compiler Pipeline - End-to-end compilation with stage control.
Supports direct input, test discovery, macro expansion, inline comments,
and optional semantic/transform/render stages.
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Optional, Any, Dict, Tuple

from lexer import Lexer, pre_scan, load_pre_scan_config
from parser import Parser, setup_grammar
from core.define import FileManager, ParseError, GrammarRulesRegister
from core.config_registry import ConfigRegistry, config
from parser.rule_selector import RuleSelector
from transform.pre.normalizer import normalize_ast
from renderer.renderer import Renderer
from analyzer import SemanticAnalyzer
from transform.post import AstTransformer
from transform.post.engine import ConfigDrivenTransform
from preprocessor import preprocess, protect_and_reverse, load_macro_config
from renderer.inline_comment import inject_comments


# ========== 配置声明（启动时由 ConfigRegistry.load_all() 统一加载）==========
config.declare("analyzer.mapping",
               file="_analyzer.toml",
               section="mapping",
               base="ext",
               required=False,
               description="增强层语义映射配置（扩展规则目录）")

# 模块级共享管线状态：组件按 rules_dir 缓存，避免重复初始化
_PIPELINE_SHARED: dict = {}

from scripts.ast_debug import (
    enable_ast_debug,
    dump_ast_compact,
    dump_tokens,
    count_ast_nodes,
)

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Force stdout to UTF-8
sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)


# ---------------------------- Helpers ----------------------------
def find_test_file(test_name: str, hint: str = "") -> Tuple[str, str, str]:
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


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_json(data: Any, path: str, label: str = "", log_fn=None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if label:
        (log_fn or print)(f"[{label}] saved ({os.path.getsize(path)} bytes)")


# ---------------------------- Core Pipeline ----------------------------
def run_pipeline_on_source(
    source: str,
    input_path: Optional[str] = None,
    out_dir: Optional[str] = None,
    expand_macros: bool = False,
    inline_comments: bool = False,
    debug: bool = False,
    quiet: bool = False,
    analyzer_enabled: bool = True,
    transform_enabled: bool = True,
    renderer_enabled: bool = True,
    stage: Optional[str] = None,
    global_recovery: bool = False,
    rules_dir: str = "pyv_compiler/grammar/rules_verilog",
    ext_dir: str = "pyv_compiler/grammar/rules_verilog_ext",
) -> Dict[str, Any]:
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
            out_dir = os.path.join(os.path.dirname(__file__), "output")
    gen_dir = os.path.join(out_dir, "gen")
    ast_dir = os.path.join(out_dir, "ast")
    sym_dir = os.path.join(out_dir, "symbols")
    lex_dir = os.path.join(out_dir, "lex")
    ensure_dir(gen_dir)
    ensure_dir(ast_dir)
    ensure_dir(sym_dir)
    ensure_dir(lex_dir)

    # Base filename for intermediate files
    if input_path:
        stem = os.path.splitext(os.path.basename(input_path))[0]
        base_name = stem.replace("ref_", "")
    else:
        base_name = "input"

    gen_file = os.path.join(gen_dir, f"gen_{base_name}.v")
    ast_json = os.path.join(ast_dir, f"{base_name}.json")
    sym_json = os.path.join(sym_dir, f"{base_name}.json")
    comment_json = os.path.join(ast_dir, f"{base_name}_comments.json")

    flags = []
    if expand_macros:
        flags.append("--expand-macros")
    if inline_comments:
        flags.append("--inline-comments")

    # ---- Stage: Preprocess ----
    macro_table = {}
    directive_lines = []
    if expand_macros:
        source, macro_table, directive_lines = preprocess(source, rules_dir)
        _log(f"[preprocessor] macros defined: {len(macro_table)}")

    # ---- Stage: Shared pipeline context (rules, lexer, renderer, etc.) ----
    # 所有按 rules_dir 可复用的组件集中初始化并缓存
    ctx = _PIPELINE_SHARED
    if rules_dir not in ctx:
        # 统一加载所有 ConfigRegistry 声明
        ConfigRegistry.load_all(rules_dir, ext_dir=ext_dir)

        # 语法规则（含 EXT 注入）
        rules = setup_grammar(rules_dir, GrammarRulesRegister.get_default(), ext_dir)
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case")
            and r.has_pass_end_case()
        ]
        rule_selector = RuleSelector(rules, stmt_names, cache_enabled=False)
        lexer = Lexer(rules_dir=rules_dir)
        renderer = Renderer(rules_dir=rules_dir)
        transformer = AstTransformer()
        transformer.register(
            ConfigDrivenTransform(
                rules=rules
            )
        )
        ctx[rules_dir] = {
            "rules": rules,
            "rule_selector": rule_selector,
            "lexer": lexer,
            "renderer": renderer,
            "transformer": transformer,
        }
    shared = ctx[rules_dir]
    rules = shared["rules"]
    rule_selector = shared["rule_selector"]
    lexer = shared["lexer"]
    renderer = shared["renderer"]
    transformer = shared["transformer"]

    # ---- Stage: Lexical analysis ----
    tokens = lexer.tokenize(source)
    if not quiet:
        tok_path = os.path.join(lex_dir, f"tokens_{base_name}.txt")
        with open(tok_path, "w", encoding="utf-8") as f:
            for tok in tokens:
                f.write(f"{tok.column},{tok.line}:{tok.type} {tok.content}\n")
    _log(f"[lexer] tokens: {len(tokens)}")
    if stage == "lex":
        result["success"] = True
        return result

    # ---- Stage: Pre-scan ----
    pre_scan_config = load_pre_scan_config(rules_dir)
    pre_symbols = pre_scan(source, pre_scan_config)
    if pre_symbols:
        _log(f"[prescan] symbols: {len(pre_symbols)}")

    # ---- Stage: Parse ----
    # Instantiate Parser with injected rules and rule_selector
    parser = Parser(
        rules_dir=rules_dir,
        cache_enabled=False,
        pre_symbols=pre_symbols,
        global_recovery=global_recovery,
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

    if not quiet:
        save_json(ast.dump(), ast_json, "ast", log_fn=_log)

    # Save comment table
    ct = getattr(parser, "_comment_table", None)
    if ct:
        if not quiet:
            save_json(ct, comment_json, "comments", log_fn=_log)
        _log(f"[comments] {len(ct)} items")

    # ---- Stage: Semantic analysis ----
    analyzer = None
    if analyzer_enabled:
        analyzer = SemanticAnalyzer(rules)

        # 从 ConfigRegistry 获取增强层语义映射配置
        try:
            mapping_cfg = config.get("analyzer.mapping")
            if mapping_cfg:
                analyzer._mapping_config = [
                    v for v in mapping_cfg.values()
                    if isinstance(v, dict) and "trigger" in v
                ]
        except KeyError:
            pass
        ast = analyzer.analyze(ast)
        if analyzer.root_scope is None:
            _log("[analyzer] warning: no scope produced")
        else:
            if not quiet:
                save_json(
                    analyzer.root_scope.to_dict(), sym_json, "symbols", log_fn=_log
                )
            _log(f"[symbols] {len(analyzer.all_symbols)} symbols")
        if analyzer.has_errors:
            for err in analyzer.errors:
                _log(f"[analyzer] ERROR {err}")
            for ref in analyzer._unresolved_refs:
                _log(f"[analyzer] WARN {ref}")
            if analyzer.errors:
                result["error"] = "; ".join(analyzer.errors)
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
        # 语义映射表：分析器产出 raw 数据，管线在此做数据变换
        mapping = analyzer.semantic_mapping

        # 解析 revert 关系：将 type_revert 条目展开为实际端口
        # 例: type_revert.spi.slave = "master" → 复制 spi.master 的端口并反转方向
        type_ports = mapping.get("type_ports_flat", {})
        type_revert = mapping.get("type_revert", {})
        if type_revert and type_ports:
            from copy import deepcopy

            def _rev_dir(d: str) -> str:
                return (
                    "output" if d in ("input", "input_reg")
                    else "input" if d in ("output", "output_reg")
                    else d
                )

            for type_name, roles in type_revert.items():
                for role_name, target_role in roles.items():
                    # 查 target 角色的端口
                    target_ports = type_ports.get(type_name, {}).get(target_role)
                    if not target_ports:
                        continue
                    # 复制并反转方向
                    resolved = []
                    for p in target_ports:
                        rev = deepcopy(p)
                        rev["direction"] = _rev_dir(rev.get("direction", ""))
                        resolved.append(rev)
                    # 设为本角色的端口
                    type_ports.setdefault(type_name, {})[role_name] = resolved

        # 注入处理后的映射表到 transform 插件
        for plugin in transformer.plugins:
            if hasattr(plugin, "set_tables"):
                plugin.set_tables(mapping)
        ast = transformer.transform(ast, scope)
        # 收集变换统计
        total = 0
        parts = []
        for plugin in transformer.plugins:
            if hasattr(plugin, "stats"):
                s = plugin.stats
                for k, v in s.items():
                    if v:
                        parts.append(f"{k}={v}")
                        total += v
        if parts:
            _log(f"[transform] {' '.join(parts)}")
    elif transform_enabled:
        _log("[transform] skipped (analyzer=None or no scope)")
    if stage == "transform":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: Render ----
    if renderer_enabled:
        content = renderer.render(ast)

        # Reverse macro protection
        if macro_table:
            macro_raw = load_macro_config(rules_dir)
            define_kw = macro_raw.get("directives", {}).get("define", "define")
            content = protect_and_reverse(
                content, original_source, macro_table,
                define_keyword=define_kw, lexer=lexer,
            )
            _log("[preprocessor] macros reversed")

        # Restore directive lines
        if directive_lines:
            content = "\n".join(directive_lines) + "\n" + content
            _log(f"[preprocessor] directives restored: {len(directive_lines)}")

        # Inline comment injection
        if inline_comments:
            raw_inline = getattr(parser, "_inline_comments", None)
            if raw_inline:
                if isinstance(raw_inline, list):
                    ic = raw_inline
                elif isinstance(raw_inline, dict):
                    ic = []
                    for line_num, info in raw_inline.items():
                        if (
                            isinstance(info, dict)
                            and "text" in info
                            and "fingerprint" in info
                        ):
                            ic.append(
                                {
                                    "line": line_num,
                                    "text": info["text"],
                                    "fingerprint": info["fingerprint"],
                                }
                            )
                        else:
                            if "line" not in info:
                                info["line"] = line_num
                            ic.append(info)
                else:
                    ic = []
                if ic:
                    content = inject_comments(content, ic)
                    _log(f"[comments] inline fingerprint injection: {len(ic)} items")

        # Write output
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"// Generated by PyV Compiler at {stamp}\n\n"
        with open(gen_file, "w", encoding="utf-8") as f:
            f.write(header + content)
        _log(f"[output] {gen_file}")

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
        "--expand-macros", action="store_true", help="Expand `define macros"
    )
    parser.add_argument(
        "--inline-comments",
        action="store_true",
        help="Re-inject inline comment fingerprints",
    )
    parser.add_argument(
        "--recovery",
        action="store_true",
        help="Enable production-level error recovery (slower, default off)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress log output and skip JSON/symbol file saves",
    )

    parser.add_argument(
        "--rules-dir",
        type=str,
        default="pyv_compiler/grammar/rules_verilog",
        help="Core grammar rules directory",
    )
    parser.add_argument(
        "--ext-dir",
        type=str,
        default="pyv_compiler/grammar/rules_verilog_ext",
        help="Extended grammar rules directory",
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
        analyzer_enabled=args.analyzer,
        transform_enabled=args.transform,
        renderer_enabled=args.renderer,
        stage=args.stage,
        global_recovery=args.recovery,
        rules_dir=args.rules_dir,
        ext_dir=args.ext_dir,
    )

    if not result["success"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
