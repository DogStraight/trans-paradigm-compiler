import sys, os
sys.path.insert(0, '.')
from core.config_registry import ConfigRegistry
from parser import Parser, setup_grammar
from core.define import GrammarRulesRegister
from lexer import Lexer

cr = ConfigRegistry()
cr.load_all(rules_dir='grammar/verilog', plugins_dir='grammar/verilog/plugins')
rules = setup_grammar('grammar/verilog', GrammarRulesRegister.get_default())
lex = Lexer(rules_dir='grammar/verilog')

# Same structure as param_hex_space but without hex spaces
src = '''module test #(
    parameter [31:0] MASK = 32'hffff_ffff
)(
    input clk
);
endmodule'''

tokens = lex.tokenize(src)
parser = Parser(rules=rules)
ast = parser.parse(tokens)
print('Without hex space:')
print(ast.dump())

# With hex space
src2 = '''module test2 #(
    parameter [31:0] MASK = 32'h ffff_ffff
)(
    input clk
);
endmodule'''
tokens2 = lex.tokenize(src2)
parser2 = Parser(rules=rules)
ast2 = parser2.parse(tokens2)
print()
print('With hex space:')
print(ast2.dump())
