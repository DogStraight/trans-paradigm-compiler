#!/usr/bin/env python3
"""
renderer-debug — 渲染诊断脚本

对指定测试用例渲染产物进行 Doc IR 树分析，
跟踪 layout 求值过程和 flat/broken 选择。

用法:
    python trace_render.py <test_name>
    python trace_render.py <test_name> --show-doc    # 显示完整 Doc IR 树
    python trace_render.py <test_name> --node <name> # 只追踪特定节点类型
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)))
sys.path.insert(0, PROJECT_ROOT)

RULES_DIR = "pyv_compiler/grammar/rules_verilog"

from lexer import Lexer
from parser import Parser
from core.define import GrammarRulesRegister
from parser.rule_selector import RuleSelector
from renderer.renderer import Renderer
from transform.pre.normalizer import normalize_ast
from renderer.doc import Doc, Text, Line, Break, Concat, Nest, Union, Empty


def dump_doc(d: Doc, indent: int = 0, max_depth: int = 10,
             target_node: str = "") -> None:
    """递归打印 Doc IR 树"""
    if indent > max_depth:
        return
    pfx = "  " * indent

    if isinstance(d, Text):
        text = repr(d.text[:60])
        print(f"{pfx}Text({text})")
    elif isinstance(d, Line):
        print(f"{pfx}Line(indent={d.indent})")
    elif isinstance(d, Break):
        print(f"{pfx}Break(indent={d.indent})")
    elif isinstance(d, Concat):
        print(f"{pfx}Concat(")
        for sub in d.docs:
            dump_doc(sub, indent + 1, max_depth, target_node)
        print(f"{pfx})")
    elif isinstance(d, Nest):
        print(f"{pfx}Nest(indent={d.indent},")
        dump_doc(d.doc, indent + 1, max_depth, target_node)
        print(f"{pfx})")
    elif isinstance(d, Union):
        print(f"{pfx}Union(")
        print(f"{pfx}  flat=")
        dump_doc(d.flat, indent + 2, max_depth, target_node)
        print(f"{pfx}  broken=")
        dump_doc(d.broken, indent + 2, max_depth, target_node)
        print(f"{pfx})")
    elif isinstance(d, Empty):
        print(f"{pfx}Empty")
    else:
        print(f"{pfx}{type(d).__name__}")


def trace(test_name: str, show_doc: bool = False, target_node: str = "") -> None:
    # 加载
    register = GrammarRulesRegister()
    rules = register.rules_registration(RULES_DIR)

    parser = Parser(rules_dir=RULES_DIR)
    parser.grammar_rules = rules
    parser.statement_rule_names = [
        name for name, rule in rules.items()
        if getattr(rule, "end_case", []) and name != "Expression"
    ]
    parser.rule_selector = RuleSelector(rules, parser.statement_rule_names)
    parser.atomic_rules = sorted(
        (rule for rule in rules.values() if getattr(rule, "is_atom", False)),
        key=lambda r: len(getattr(r, "production", [])),
        reverse=True,
    )

    lex = Lexer(rules_dir=RULES_DIR)
    renderer = Renderer(RULES_DIR)

    # 源文件
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

    # 解析
    tokens = lex.tokenize(source)
    ast = parser.parse(tokens)
    if ast is None:
        print("Error: parser returned None")
        sys.exit(1)

    # 归一化
    norm = normalize_ast(ast, renderer._layouts)

    # 获取布局配置并构建 Doc IR
    layouts = renderer._layouts

    def trace_node(node, depth: int = 0):
        name = node.node_name
        if target_node and name != target_node:
            return
        layout = layouts.get(name, {})
        pfx = "  " * depth

        print(f"{pfx}{name}")
        if layout:
            head = layout.get("layout") or layout.get("head")
            body_cfg = layout.get("body")
            tail_cfg = layout.get("tail")
            if head:
                print(f"{pfx}  head: {_summarize(head)}")
            if body_cfg:
                print(f"{pfx}  body: {_summarize(body_cfg)}")
            if tail_cfg:
                print(f"{pfx}  tail: {_summarize(tail_cfg)}")
        else:
            print(f"{pfx}  (no layout)")

        # 递归子节点
        for attr in vars(node):
            if attr in ("node_name", "start", "end", "sub_node") or attr.startswith("_"):
                continue
            val = getattr(node, attr)
            if isinstance(val, type(node)):
                trace_node(val, depth + 1)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, type(node)):
                        trace_node(item, depth + 1)

    def _summarize(cfg):
        if isinstance(cfg, str):
            return repr(cfg[:40])
        if isinstance(cfg, dict):
            items = []
            for k, v in cfg.items():
                if isinstance(v, dict):
                    items.append(f"{k}={{...}}")
                elif isinstance(v, list):
                    items.append(f"{k}=[{len(v)} items]")
                else:
                    items.append(f"{k}={repr(v)[:30]}")
            return ", ".join(items)
        return ""

    print(f"\n{'='*60}")
    print(f"  Renderer Trace — {test_name}")
    print(f"{'='*60}")

    # 布局树概览
    print(f"\n  Layout Tree:")
    for child in norm.sub_node if hasattr(norm, "sub_node") else []:
        trace_node(child)

    # 渲染输出
    output = renderer.render(norm)
    print(f"\n  Rendered Output ({len(output)} chars, "
          f"{len([l for l in output.split(chr(10)) if l.strip()])} lines):")
    for line in output.split("\n")[:6]:
        print(f"    {line}")
    if output.count("\n") > 5:
        print(f"    ... ({output.count(chr(10)) - 4} more lines)")

    # Doc IR 树
    if show_doc:
        print(f"\n  Doc IR Tree:")
        doc = renderer._render_node(norm, layouts.get(norm.node_name, {}), 0)
        dump_doc(doc, max_depth=8, target_node=target_node)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Renderer trace")
    parser.add_argument("test_name", help="Test case name")
    parser.add_argument("--show-doc", action="store_true", help="Show Doc IR tree")
    parser.add_argument("--node", help="Filter by node type")
    args = parser.parse_args()
    trace(args.test_name, show_doc=args.show_doc, target_node=args.node or "")
