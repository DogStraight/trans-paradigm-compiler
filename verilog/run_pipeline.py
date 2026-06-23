#!/usr/bin/env python3
"""
PyV 编译器端到端测试
使用 verilog/ref_*.v 作为输入，用 Verilog 语法规则解析，
再用 Renderer 生成代码，并与参考文件对比。

用法:
    python run_pipeline.py                    # 默认 led_blinker_ref.v
    python run_pipeline.py ref_counter        # 测试计数器
    python run_pipeline.py ref_fsm            # 测试状态机
    python run_pipeline.py ref_top            # 测试顶层模块
    python run_pipeline.py ref_alu            # 测试 ALU
    python run_pipeline.py ref_dff            # 测试 D 触发器
"""

import sys, os
from core.define import Node

sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from lexer import Lexer
from parser import Parser
from core.define import GrammarRulesRegister
from parser.rule_selector import RuleSelector
from transform.pre.normalizer import normalize_ast
from renderer.renderer import Renderer
from analyzer import SemanticAnalyzer
from transform.post import AstTransformer
from scripts.ast_debug import enable_ast_debug, dump_ast_compact, dump_tokens, count_ast_nodes
import json

# 可选：后阶段变换插件
# from transform.post.plugins.implicit_decl import ImplicitDeclPlugin
# from transform.post.plugins.width_eval import WidthEvalPlugin


def pipeline():
    # 支持命令行参数
    #   python run_pipeline.py [test_name] [--debug]
    #   python run_pipeline.py --debug ref_complex
    debug = enable_ast_debug()  # 先读环境变量
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if '--debug' in flags:
        debug = enable_ast_debug(True)
        print('🔍 调试模式已开启')

    if args:
        arg = args[0].replace("ref_", "").replace(".v", "")
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
    sym_dir = os.path.join(src_dir, "symbols")
    os.makedirs(gen_dir, exist_ok=True)
    os.makedirs(ast_dir, exist_ok=True)
    os.makedirs(sym_dir, exist_ok=True)
    gen_file = os.path.join(gen_dir, "gen_" + stem.replace("ref_", "") + ".v")
    ast_json = os.path.join(ast_dir, stem.replace("ref_", "") + ".json")
    sym_json = os.path.join(sym_dir, stem.replace("ref_", "") + ".json")

    # 1. 读取源文件
    with open(src_file, "r", encoding="utf-8") as f:
        source = f.read()
    print(f"📄 源文件: {src_file}")

    RULES_DIR = "pyv_compiler/grammar/rules_verilog"

    # 2. 词法分析
    lexer = Lexer(rules_dir=RULES_DIR)
    tokens = lexer.tokenize(source)
    lex_dir = os.path.join(src_dir, "lex")
    os.makedirs(lex_dir, exist_ok=True)
    with open(
        os.path.join(lex_dir, "tokens_" + stem + ".txt"),
        "w",
        encoding="utf-8",
    ) as f:
        for token in tokens:
            f.write(f"{token.column},{token.line}:{token.type} {token.content}\n")
    print(f"🔤 Token 数: {len(tokens)}")

    # 3. 语法分析（使用 Verilog 规则）
    register = GrammarRulesRegister()
    rules = register.rules_registration(RULES_DIR)

    # 设定起始 token 缓存路径（避免每次重建）
    cache_dir = os.path.join(src_dir, "..", "grammar")
    cache_path = os.path.normpath(os.path.join(cache_dir, "start_token_cache.json"))
    from parser.rule_selector import set_default_cache_path
    set_default_cache_path(cache_path)

    parser = Parser(rules_dir=RULES_DIR)
    parser.grammar_rules = rules
    parser.statement_rule_names = [
        name for name, rule in rules.items() if rule.end_case and name != "Expression"
    ]
    parser.rule_selector = RuleSelector(rules, parser.statement_rule_names)
    parser.atomic_rules = sorted(
        (rule for rule in rules.values() if getattr(rule, "atomic", False)),
        key=lambda r: len(r.production),
        reverse=True,
    )

    ast = parser.parse(tokens)
    if ast is None:
        print("❌ 语法分析失败")
        return

    if debug:
        print(f"🔍 AST 节点数 (原始): {count_ast_nodes(ast)}")

    # 4. AST 规范化（翻译 parser 内部构造为规范形式）
    ast = normalize_ast(ast)

    if debug:
        print(f"🔍 AST 节点数 (规范化后): {count_ast_nodes(ast)}")
        print("🔍 AST 结构 (摘要):")
        dump_ast_compact(ast)
        print()
        if len(tokens) <= 150:
            print("🔍 Token 流:")
            dump_tokens(tokens)

    # 保存规范化的 AST（覆盖 ast_json）
    with open(ast_json, "w", encoding="utf-8") as f:
        json.dump(ast.dump(), f, indent=2)
    print(f"📋 AST 已保存 ({os.path.getsize(ast_json)} bytes)")

    # 5. 语义分析（构建符号表，链接标识符到声明）
    #     核心职责：管理作用域 + 注册显式声明的符号
    #     高级服务（隐式声明、位宽计算等）在可选的 transform 插件中完成
    global analyzer_enable
    if analyzer_enable:
        analyzer = SemanticAnalyzer(rules)
        ast = analyzer.analyze(ast)
        scope = analyzer.root_scope
        assert scope is not None, "语义分析后 root_scope 不应为空"
        with open(sym_json, "w", encoding="utf-8") as f:
            json.dump(scope.to_dict(), f, indent=2)
        print(
            f"🔗 符号表已保存 ({os.path.getsize(sym_json)} bytes, {len(analyzer.all_symbols)} symbols)"
        )

    # 6. 后阶段 AST 变换（可选插件管线）
    global transform_enable
    if transform_enable and analyzer_enable:
        transformer = AstTransformer()
        # 按需注册插件，例如:
        # transformer.register(ImplicitDeclPlugin())
        # transformer.register(WidthEvalPlugin())
        ast = transformer.transform(ast, scope)

    # 7. 代码生成（使用 Renderer）
    global renderer_enable
    if renderer_enable:
        renderer = Renderer(rules_dir=RULES_DIR)
        content = renderer.render(ast)

        from datetime import datetime
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"// Generated by PyV Compiler at {stamp}\n\n"
        with open(gen_file, "w", encoding="utf-8") as f:
            f.write(header + content)
        print(f"✅ 已生成: {gen_file}")


if __name__ == "__main__":
    analyzer_enable = True  # 语义分析（作用域 + 符号注册）
    transform_enable = False  # 后阶段变换插件管线（默认关闭）
    renderer_enable = True  # 代码生成
    pipeline()
