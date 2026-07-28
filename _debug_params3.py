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

src = open('verilog/tests/normal/ref/ref_param_hex_space.v', encoding='utf-8').read()
tokens = lex.tokenize(src)
print(f'Total tokens: {len(tokens)}')
print('All tokens (non-trivia):')
for i, t in enumerate(tokens):
    if t.type not in ('newline', 'space', 'space.fold'):
        print(f'  [{i:3d}] {t.type:25s} {t.content!r:15s} Ln {t.line}')

print()
print('Source length:', len(src))
print('Reprint:')
for i, ch in enumerate(src[:100]):
    print(f'{i:3d} {ch!r:4s}', end='  ')
    if (i+1) % 10 == 0:
        print()
