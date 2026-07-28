import sys, os
sys.path.insert(0, '.')
sys.path.insert(0, 'verilog')
from core.config_registry import ConfigRegistry
from parser import Parser, setup_grammar
from core.define import GrammarRulesRegister
from lexer import Lexer

cr = ConfigRegistry()
cr.load_all(rules_dir='grammar/verilog', plugins_dir='grammar/verilog/plugins')
rules = setup_grammar('grammar/verilog', GrammarRulesRegister.get_default())
lex = Lexer(rules_dir='grammar/verilog')

# Test with simple module that has params
src = '''module test #(parameter W = 8)(); endmodule'''
tokens = lex.tokenize(src)
print('Tokens:')
for i, t in enumerate(tokens):
    if t.type not in ('newline', 'space', 'space.fold'):
        print(f'  {i}: {t.type} = {t.content!r}')

parser = Parser(rules=rules)
ast = parser.parse(tokens)
print()
print('AST:')
print(ast.dump())

print()
# Now test param_hex_space
src2 = open('verilog/tests/normal/ref/ref_param_hex_space.v', encoding='utf-8').read()
tokens2 = lex.tokenize(src2)
parser2 = Parser(rules=rules)
ast2 = parser2.parse(tokens2)
print('param_hex_space AST:')
print(ast2.dump())
