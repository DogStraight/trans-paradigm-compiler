import sys, os
sys.path.insert(0, '.')
from linter.scanner import LinterScanner
from linter.grammar_slicer import build_slice_tree
from core.define import GrammarRulesRegister
from parser import setup_grammar
from core.config_registry import ConfigRegistry

RD = 'grammar/verilog'

# Check depth of key rules
cr = ConfigRegistry()
cr.load_all(rules_dir=RD, plugins_dir=RD + '/plugins')
rules = setup_grammar(RD, GrammarRulesRegister.get_default())
tree = build_slice_tree(rules)

def depth(info):
    if info.get("pratt") or info.get("is_atom"): return "atom"
    if info.get("is_block"): return "block"
    if info.get("is_statement"): return "shallow"
    if info.get("prods"): return "full"
    return "atom"

print('=== Rule depths ===')
for name in ['AnsiInputDecl','AnsiOutputDecl','AnsiInoutDecl',
             'AnsiPortDecl','PortList','PortParens',
             'TypeSpecNoReg','DeclaratorList','Range','SelectSuffix',
             'TaskAnsiInputDecl','TaskPortList']:
    info = tree.get(name)
    if info:
        d = depth(info)
        stmt = info.get('is_statement')
        print(f'  {name:20s} depth={d:8s} is_statement={stmt} prods={bool(info.get("prods"))}')

# Trace: choice error poisoning first_silent
print('\n=== Pattern A: choice error poisoning ===')
l = LinterScanner(rules_dir=RD, enable_phase1=False, enable_phase2=False, enable_phase3=True)
l.debug_p3 = True
src = open('verilog/tests/normal/ref/ref_simple_func.v', encoding='utf-8').read()
errs = l.scan(src)

# Show only _match_choice events
for t in l._p3_trace_log:
    if 'alt#' in t or 'choice' in t:
        print(t)
    if 'exit' in t and 'first_elem_errored' in t:
        print(t)
