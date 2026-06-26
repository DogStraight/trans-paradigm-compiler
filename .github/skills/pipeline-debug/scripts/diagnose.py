#!/usr/bin/env python3
"""
pipeline-debug — 管线诊断脚本

对指定测试用例执行全流程诊断，输出结构化报告。
用于快速定位解析失败的原因。

用法:
    python diagnose.py <test_name>              # 如 led_blinker, counter
    python diagnose.py <test_name> --verbose     # 详细输出
    python diagnose.py <test_name> --no-render   # 跳过渲染阶段
"""

import sys
import os
import json

# ── 项目路径 ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)))
sys.path.insert(0, PROJECT_ROOT)

RULES_DIR = "pyv_compiler/grammar/rules_verilog"

from lexer import Lexer
from parser import Parser
from core.define import GrammarRulesRegister
from parser.rule_selector import RuleSelector, build_start_token_map_names
from renderer.renderer import Renderer
from transform.pre.normalizer import normalize_ast
from core.define import Node as AstNode

# ── 诊断结果收集 ──

class Report:
    def __init__(self):
        self.tokens = []
        self.token_count = 0
        self.warnings = []
        self.ast_raw = None
        self.ast_norm = None
        self.ast_node_count = 0
        self.render_output = ""
        self.render_lines = 0
        self.candidates_per_token = {}
        self.rule_count = 0
        self.statement_rule_count = 0

    def print(self, verbose: bool = False):
        W = "\\n".join
        print(f"\\n{'='*60}")
        print(f"  Pipeline Diagnosis Report")
        print(f"{'='*60}")

        print(f"\\n  Tokens: {self.token_count}")
        if self.token_count <= 100 or verbose:
            for t in self.tokens[:20]:
                print(f"    [{t['pos']:3d}] {t['type']:30s} {repr(t['content'])}")
            if self.token_count > 20:
                print(f"    ... ({self.token_count - 20} more)")

        print(f"\\n  Rules: {self.rule_count} total, {self.statement_rule_count} statement rules")

        if self.warnings:
            print(f"\\n  Warnings ({len(self.warnings)}):")
            for w in self.warnings[:20]:
                print(f"    {w}")
            if len(self.warnings) > 20:
                print(f"    ... ({len(self.warnings) - 20} more)")

        print(f"\\n  AST: {self.ast_node_count} nodes (raw), {self.ast_norm_node_count} nodes (normalized)")
        if self.ast_node_count <= 20:
            self._print_ast(self.ast_raw, 0)

        if self.render_output:
            lines = self.render_output.split("\\n")
            print(f"\\n  Render: {self.render_lines} lines, {len(self.render_output)} chars")
            for line in lines[:5]:
                print(f"    {line}")
            if len(lines) > 5:
                print(f"    ... ({len(lines) - 5} more lines)")

    def _print_ast(self, node, depth):
        if isinstance(node, list):
            for item in node[:10]:
                self._print_ast(item, depth)
            if len(node) > 10:
                print(f"{'  '*(depth+1)}... ({len(node)-10} more)")
        elif isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    print(f"{'  '*depth}{k}:")
                    self._print_ast(v, depth+1)
                else:
                    print(f"{'  '*depth}{k}: {repr(v)[:60]}")
        else:
            print(f"{'  '*depth}{repr(node)[:60]}")


def diagnose(test_name: str, verbose: bool = False, no_render: bool = False) -> Report:
    report = Report()

    # ── 源文件 ──
    src_dir = os.path.join(PROJECT_ROOT, "verilog", "ref")
    stem = test_name.replace("ref_", "")
    src_file = os.path.join(src_dir, f"ref_{stem}.v")
    if not os.path.exists(src_file):
        src_file = os.path.join(src_dir, f"{stem}.v")
    if not os.path.exists(src_file):
        src_file = os.path.join(src_dir, f"{test_name}.v")
    if not os.path.exists(src_file):
        print(f"Error: source file not found for '{test_name}'")
        sys.exit(1)

    with open(src_file, encoding="utf-8") as f:
        source = f.read()

    # ── 加载规则 ──
    register = GrammarRulesRegister()
    rules = register.rules_registration(RULES_DIR)
    report.rule_count = len(rules)

    # ── 1. Teken 流 ──
    lex = Lexer(rules_dir=RULES_DIR)
    tokens = lex.tokenize(source)
    report.token_count = len(tokens)
    report.tokens = [
        {"pos": i, "type": t.type, "content": t.content}
        for i, t in enumerate(tokens)
    ]

    # ── 2. 候选规则映射 ──
    statement_rule_names = [
        name for name, rule in rules.items()
        if getattr(rule, "end_case", []) and name != "Expression"
    ]
    report.statement_rule_count = len(statement_rule_names)
    start_map = build_start_token_map_names(rules, statement_rule_names)

    # 对每个 token 检查候选规则数
    seen_tokens = set()
    for t in tokens:
        if t.type not in seen_tokens:
            seen_tokens.add(t.type)
            candidates = start_map.get(t.type, [])
            report.candidates_per_token[t.type] = candidates

    # ── 3. 解析 ──
    parser = Parser(rules_dir=RULES_DIR)
    parser.grammar_rules = rules
    parser.statement_rule_names = statement_rule_names
    parser.rule_selector = RuleSelector(rules, parser.statement_rule_names)
    parser.atomic_rules = sorted(
        (rule for rule in rules.values() if getattr(rule, "atomic", False)),
        key=lambda r: len(getattr(r, "production", [])),
        reverse=True,
    )

    # 捕获 _warn 输出
    original_warn = parser._warn
    parser._warn = lambda msg: report.warnings.append(msg)

    ast = parser.parse(tokens)
    parser._warn = original_warn

    # ── 4. AST ──
    if ast is None:
        print("  Error: parser returned None")
        report.ast_raw = {}
        report.ast_norm = {}
    else:
        report.ast_raw = ast.dump()
        report.ast_node_count = count_nodes(ast)
        ast = normalize_ast(ast)
        report.ast_norm = ast.dump() if isinstance(ast, AstNode) else ast
        report.ast_norm_node_count = count_nodes(ast) if isinstance(ast, AstNode) else 0

    # ── 5. 渲染 ──
    if not no_render:
        renderer = Renderer(rules_dir=RULES_DIR)
        try:
            output = renderer.render(ast if ast else AstNode("Root"))
            report.render_output = output
            report.render_lines = len([l for l in output.split("\\n") if l.strip()])
        except Exception as e:
            report.render_output = f"Render error: {e}"

    return report


def count_nodes(node) -> int:
    if isinstance(node, list):
        return sum(count_nodes(n) for n in node)
    if isinstance(node, AstNode):
        count = 1
        for attr in vars(node).values():
            if isinstance(attr, list):
                count += sum(count_nodes(n) for n in attr if isinstance(n, AstNode))
            elif isinstance(attr, AstNode):
                count += count_nodes(attr)
        return count
    return 0


# ── 入口 ──

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline diagnosis")
    parser.add_argument("test_name", help="Test case name (e.g. led_blinker)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed output")
    parser.add_argument("--no-render", action="store_true", help="Skip rendering")
    parser.add_argument("--trace-token", help="Trace candidate rules for a specific token type")
    args = parser.parse_args()

    if args.trace_token:
        # 单独运行 Token 追踪
        register = GrammarRulesRegister()
        rules = register.rules_registration(RULES_DIR)
        statement_rule_names = [
            name for name, rule in rules.items()
            if getattr(rule, "end_case", []) and name != "Expression"
        ]
        start_map = build_start_token_map_names(rules, statement_rule_names)
        candidates = start_map.get(args.trace_token, [])
        print(f"\nCandidate rules for token '{args.trace_token}':")
        if candidates:
            for name in candidates:
                rule = rules[name]
                prods = getattr(rule, "production", [])
                end_case = getattr(rule, "end_case", [])
                inline = getattr(rule, "inline", False)
                block_start = getattr(rule, "block_start", None)
                print(f"\n  {name}")
                print(f"    production: {prods}")
                print(f"    end_case: {end_case}")
                print(f"    inline: {inline}")
                if block_start is not None:
                    print(f"    block_start: {block_start}")
        else:
            print("  (no candidates)")
        sys.exit(0)

    report = diagnose(args.test_name, verbose=args.verbose, no_render=args.no_render)
    report.print(verbose=args.verbose)
