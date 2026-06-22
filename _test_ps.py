"""测试 PartSelect 解析"""
import sys; sys.path.insert(0,'.')
from lexer.main_lexer import Lexer
from parser.main_parser import Parser, ParseContext
from core.define import GrammarRulesRegister, Node
from parser.rule_selector import RuleSelector

RULES_DIR = 'pyv_compiler/grammar/rules_verilog'

text = '''module t();
    wire [7:0] v;
    assign x = v[3:0];
endmodule'''
tokens = Lexer(rules_dir=RULES_DIR).tokenize(text)

register = GrammarRulesRegister()
rules = register.rules_registration(RULES_DIR)
parser = Parser(rules_dir=RULES_DIR)
parser.grammar_rules = rules
parser.statement_rule_names = [n for n,r in rules.items() if getattr(r,'end_case',None) and n != 'Expression']
parser.rule_selector = RuleSelector(rules, parser.statement_rule_names)
parser.atomic_rules = sorted((rule for rule in rules.values() if getattr(rule,'atomic',False)), key=lambda r: len(r.production), reverse=True)

ast = parser.parse(tokens)
if ast:
    print('Parse OK')
    def walk(n, depth=0):
        nn = getattr(n, 'node_name', type(n).__name__)
        if depth > 0:
            print(f'{"  "*depth}{nn}')
        for k in vars(n):
            v = getattr(n, k)
            if isinstance(v, Node):
                walk(v, depth+1)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, Node):
                        walk(item, depth+1)
    for child in getattr(ast, 'sub_node', []):
        walk(child)
else:
    print('Parse FAILED')
