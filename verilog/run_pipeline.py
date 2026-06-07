#!/usr/bin/env python3
"""
PyV 编译器端到端测试：LED Blinker
将 .pyv 源文件解析为 AST，再用 CG 生成目标代码。
"""

import sys, os
sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

# 确保可以从项目根目录导入
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lexer import Lexer
from parser import Parser
from code_generator import CodeGenerator
import json

def main():
    src_dir = os.path.dirname(os.path.abspath(__file__))
    src_file = os.path.join(src_dir, "led_blinker.pyv")
    out_file = os.path.join(src_dir, "led_blinker_gen.v")
    ref_file = os.path.join(src_dir, "led_blinker_ref.v")
    
    # 1. 读取源文件
    with open(src_file, 'r', encoding='utf-8') as f:
        source = f.read()
    print(f"📄 源文件: {src_file}")
    
    # 2. 词法分析
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    print(f"🔤 Token 数: {len(tokens)}")
    
    # 3. 语法分析
    parser = Parser()
    ast = parser.parse(tokens)
    if not ast:
        print("❌ 语法分析失败")
        return
    
    children = getattr(ast, 'child', [])
    print(f"🌳 AST 根节点: {[c.name if hasattr(c, 'name') else str(c) for c in children]}")
    
    # 保存 AST JSON 用于调试
    ast_json = os.path.join(src_dir, "led_blinker_ast.json")
    with open(ast_json, 'w', encoding='utf-8') as f:
        json.dump(ast.dump(), f, indent=2)
    print(f"📋 AST 已保存: {ast_json}")
    
    # 4. 代码生成
    cg = CodeGenerator()
    outputs = cg.generate(ast)
    outputs = cg.optimize(outputs)
    
    # 5. 输出
    for fname, content in outputs.items():
        filepath = os.path.join(src_dir, fname)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 已生成: {filepath}")
    
    # 6. 对比参考文件
    print(f"\n{'='*60}")
    print(f"📊 输出 vs 参考")
    print(f"{'='*60}")
    
    gen_content = outputs.get("output.v", "")
    print(f"\n--- led_blinker_gen.v (生成) ---")
    print(gen_content)
    
    if os.path.exists(ref_file):
        with open(ref_file, 'r', encoding='utf-8') as f:
            ref_content = f.read()
        print(f"\n--- led_blinker_ref.v (参考) ---")
        print(ref_content)

if __name__ == '__main__':
    main()
