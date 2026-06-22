"""调试 SelectChain 属性"""
import sys; sys.path.insert(0,'.')
from lexer.main_lexer import Lexer
from parser.main_parser import Parser
from core.define import GrammarRulesRegister
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

def find_sc(n, depth=0):
    if hasattr(n,'node_name') and 'SelectChain' in n.node_name:
        print('Found SelectChain')
        for a in vars(n):
            if not a.startswith('_'):
                v = getattr(n,a)
                print(f'  {a}: {type(v).__name__} = {v!r}')
    for k in vars(n):
        v = getattr(n,k)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, __import__('core.define',fromlist=['Node']).Node):
                    find_sc(item, depth+1)
        elif isinstance(v, __import__('core.define',fromlist=['Node']).Node):
            find_sc(v, depth+1)
find_sc(ast)
