#!/usr/bin/env python3
"""
PyV 编译器端到端测试
直接使用 verilog/ref_*.v 作为输入，用 Verilog 语法规则解析，
再用 Verilog CG 规则生成代码，并与参考文件对比。

用法:
    python run_pipeline.py                    # 默认 led_blinker_ref.v
    python run_pipeline.py ref_counter        # 测试计数器
    python run_pipeline.py ref_fsm            # 测试状态机
    python run_pipeline.py ref_top            # 测试顶层模块
    python run_pipeline.py ref_alu            # 测试 ALU
    python run_pipeline.py ref_dff            # 测试 D 触发器
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
from optimizer.ast_optimizer import optimize_ast, get_optimize_transforms
from formatter import format_code
import json
import difflib
import copy


def main():
    # 支持命令行指定测试文件
    if len(sys.argv) > 1:
        arg = sys.argv[1].replace("ref_", "").replace(".v", "")
        test_name = f"ref\\ref_{arg}"
    else:
        test_name = "ref\\ref_led_blinker"  # 默认测试文件

    src_dir = os.path.dirname(os.path.abspath(__file__))
    ref_dir = os.path.join(src_dir, "ref")
    src_file = os.path.join(ref_dir, test_name + ".v")
    if not os.path.exists(src_file):
        src_file = os.path.join(src_dir, test_name + ".v")
    if not os.path.exists(src_file):
        print(f"❌ 找不到源文件: {src_file}")
        sys.exit(1)

    stem = os.path.splitext(os.path.basename(src_file))[0]

    gen_dir = os.path.join(src_dir, "gen")
    ast_dir = os.path.join(src_dir, "ast")
    os.makedirs(gen_dir, exist_ok=True)
    os.makedirs(ast_dir, exist_ok=True)
    gen_file = os.path.join(gen_dir, "gen_" + stem.replace("ref_", "") + ".v")
    ast_json = os.path.join(ast_dir, stem.replace("ref_", "") + ".json")

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

    # 4. AST 优化（深拷贝后优化，不影响原始 AST）
    transforms = get_optimize_transforms()
    ast_opt = optimize_ast(copy.deepcopy(ast), transforms)
    ast_opt_json = ast_json.replace(".json", "_opt.json")
    with open(ast_opt_json, "w", encoding="utf-8") as f:
        json.dump(ast_opt.dump(), f, indent=2)
    print(f"⚙️  AST 优化已保存 ({os.path.getsize(ast_opt_json)} bytes)")

    # 5. 代码生成（使用优化后的 AST）
    cg = CodeGenerator(rules_dir="pyv_compiler/grammar/rules_verilog")
    outputs = cg.generate(ast_opt)
    outputs = cg.optimize(outputs)

    content = outputs.get("output.v", "")

    # 6. 格式化（缩进、块合并）
    content = format_code(content)

    with open(gen_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 已生成: {gen_file}")

    # 7. 对比
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

    # 8. 统计
    print(f"\n{'='*60}")
    print(f"  参考行数: {len(ref)}")
    print(f"  生成行数: {len(gen)}")
    print(f"  差异行数: {len(diff_lines)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
