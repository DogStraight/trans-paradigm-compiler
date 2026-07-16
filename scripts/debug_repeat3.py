import sys; sys.path.insert(0,'.'); import io
from core.config_registry import ConfigRegistry; ConfigRegistry.load_all('grammar/rules_verilog', ext_dirs=['grammar/rules_verilog_ext'])
from lexer import Lexer; lex=Lexer(rules_dir='grammar/rules_verilog', ext_dirs=['grammar/rules_verilog_ext'])
from core.define import GrammarRulesRegister; from parser import setup_grammar, Parser; from parser.rule_selector import RuleSelector
rules=setup_grammar('grammar/rules_verilog', GrammarRulesRegister.get_default(), ext_dirs=['grammar/rules_verilog_ext'])
stmt_names=[n for n,r in rules.items() if hasattr(r,'has_pass_end_case') and r.has_pass_end_case()]
sel=RuleSelector(rules,stmt_names,cache_enabled=False)
with io.open('verilog/tests/normal/ref/ref_spi_inf.v', encoding='utf-8') as f:
    src=f.read()
tokens=lex.tokenize(src)
from parser.parser_core import ParseContext; from parser._production import process_production_node, _get_prod_features
parser=Parser(rules=rules, rule_selector=sel, cache_enabled=False)

elem = {'type': 'seq', 'items': [{'type': 'token', 'token_type': 'symbol.base.comma'}, {'type': 'call', 'name': 'NamedPortConnect'}]}
ctx=ParseContext(tokens); ctx.token_pointer=107
print('Tok at T107:', ctx.peek_token().type)
snap=ctx.create_snapshot()
res=process_production_node(parser, elem, ctx)
if res is not None:
    print('Seq OK, ptr:', ctx.token_pointer)
else:
    print('Seq FAIL at ptr:', ctx.token_pointer)
    if ctx.has_more_tokens():
        print('Token:', ctx.peek_token().type, '=', ctx.peek_token().content)
    ctx.restore_snapshot(snap)
