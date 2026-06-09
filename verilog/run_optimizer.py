"""Run optimizer and save optimized AST + generated output"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from define import Node, GrammarRulesRegister
from lexer import Lexer
from parser import Parser
from parser.rule_selector import RuleSelector
from optimizer import optimize_ast, get_optimize_transforms
from code_generator import CodeGenerator

src_file = os.path.join(os.path.dirname(__file__), "led_blinker_ref.v")
with open(src_file, 'r', encoding='utf-8') as f:
    source = f.read()

register = GrammarRulesRegister()
rules = register.rules_registration("pyv_compiler/grammar/rules_verilog")
lexer = Lexer()
tokens = lexer.tokenize(source)
parser = Parser()
parser.grammar_rules = rules
parser.statement_rule_names = [n for n, r in rules.items() if r.end_case]
parser.rule_selector = RuleSelector(rules, parser.statement_rule_names)
ast = parser.parse(tokens)

optimized = optimize_ast(ast, get_optimize_transforms())

def serialize(obj):
    if isinstance(obj, Node):
        d = {}
        for a, v in obj.__dict__.items():
            if a == "name": continue
            d[a] = serialize(v)
        return {obj.name: d}
    elif isinstance(obj, list):
        return [serialize(i) for i in obj]
    return obj

opt_ast = os.path.join(os.path.dirname(__file__), "led_blinker_ast_optimized.json")
with open(opt_ast, 'w', encoding='utf-8') as f:
    json.dump(serialize(optimized), f, indent=2)
print(f"AST saved ({os.path.getsize(opt_ast)} bytes)")

cg = CodeGenerator(rules_dir="pyv_compiler/grammar/cg_rules_verilog")
out = cg.generate(optimized)
out = cg.optimize(out)
content = out.get("output.v", "")

gen = os.path.join(os.path.dirname(__file__), "led_blinker_gen_opt.v")
with open(gen, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Output saved ({os.path.getsize(gen)} bytes)")
print(content)
