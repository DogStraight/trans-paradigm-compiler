import sys, os
sys.path.insert(0, '.')
from parser import Parser, setup_grammar
from core.define import GrammarRulesRegister
from core.config_registry import ConfigRegistry
from lexer import Lexer

cr = ConfigRegistry()
cr.load_all(rules_dir='grammar/verilog', plugins_dir='grammar/verilog/plugins')
rules = setup_grammar('grammar/verilog', GrammarRulesRegister.get_default())
lex = Lexer(rules_dir='grammar/verilog')

src = '''module param_hex_space #(
    parameter [31:0] MASK = 32'h ffff_ffff
)(
    input clk
);
    always @(posedge clk) begin
    end
endmodule'''

tokens = lex.tokenize(src)
print('Tokens:')
for i, t in enumerate(tokens):
    if t.type not in ('newline', 'space', 'space.fold', 'comment'):
        print(f'  {i}: {t.type} = {t.content!r}')

parser = Parser(rules=rules)
ast = parser.parse(tokens)
print()
print('Parse result OK')
if ast:
    def dump(node, indent=0):
        rn = getattr(node, 'rule_name', '???')
        sub_nodes = getattr(node, 'sub_nodes', []) or []
        # print rule name and any non-sub_node attrs
        parts = [rn]
        for k in vars(node):
            if k not in ('sub_nodes', 'rule_name'):
                parts.append(f'{k}={getattr(node, k)}')
        print(' ' * indent + ' '.join(parts)[:150])
        for sn in sub_nodes:
            dump(sn, indent + 2)
    dump(ast)
