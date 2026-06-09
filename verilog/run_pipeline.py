#!/usr/bin/env python3
"""
PyV 编译器端到端测试：Verilog LED Blinker
直接使用 led_blinker_ref.v 作为输入，用 Verilog 语法规则解析，
再用 Verilog CG 规则生成代码，并与参考文件对比。
"""

import sys, os

sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lexer import Lexer
from parser import Parser
from code_generator import CodeGenerator, CodeGenerator
from define import GrammarRulesRegister
from parser.rule_selector import RuleSelector
import json
import difflib


def main():
    src_dir = os.path.dirname(os.path.abspath(__file__))
    src_file = os.path.join(src_dir, "led_blinker_ref.v")
    gen_file = os.path.join(src_dir, "led_blinker_gen.v")
    ast_json = os.path.join(src_dir, "led_blinker_ast.json")

    # 1. 读取源文件
    with open(src_file, "r", encoding="utf-8") as f:
        source = f.read()
    print(f"📄 源文件: {src_file}")

    # 2. 词法分析
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    print(f"🔤 Token 数: {len(tokens)}")

    # 3. 语法分析（使用 Verilog 规则）
    register = GrammarRulesRegister()
    rules = register.rules_registration("pyv_compiler/grammar/rules_verilog")
    parser = Parser()
    parser.grammar_rules = rules
    parser.statement_rule_names = [
        name for name, rule in rules.items() if rule.end_case
    ]
    parser.rule_selector = RuleSelector(rules, parser.statement_rule_names)

    ast = parser.parse(tokens)
    if not ast:
        print("❌ 语法分析失败")
        return

    children = getattr(ast, "child", [])
    print(
        f"🌳 AST 根节点: {[c.name if hasattr(c, 'name') else str(c) for c in children]}"
    )

    # 保存 AST
    with open(ast_json, "w", encoding="utf-8") as f:
        json.dump(ast.dump(), f, indent=2)
    print(f"📋 AST 已保存 ({os.path.getsize(ast_json)} bytes)")

    # 4. 代码生成（使用 Verilog CG 规则）
    cg = CodeGenerator(rules_dir="pyv_compiler/grammar/cg_rules_verilog")
    outputs = cg.generate(ast)
    outputs = cg.optimize(outputs)

    content = outputs.get("output.v", "")
    with open(gen_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 已生成: {gen_file}")

    # 5. 对比
    ref = source.splitlines(keepends=True)
    gen = content.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(ref, gen, fromfile="ref.v", tofile="gen.v", n=2)
    )

    print(f"\n{'='*60}")
    print("  DIFF (生成 vs 参考)")
    print(f"{'='*60}")
    if diff_lines:
        for line in diff_lines:
            print(line, end="")
    else:
        print("  ✨ 完全一致！")

    # 6. 统计
    print(f"\n{'='*60}")
    print(f"  参考行数: {len(ref)}")
    print(f"  生成行数: {len(gen)}")
    print(f"  差异行数: {len(diff_lines)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
