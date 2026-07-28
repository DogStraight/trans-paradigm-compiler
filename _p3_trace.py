import sys, os
sys.path.insert(0, '.')
from linter.scanner import LinterScanner

RD = 'grammar/verilog'

def trace(name, filter_fn=None):
    l = LinterScanner(rules_dir=RD, enable_phase1=False, enable_phase2=False, enable_phase3=True)
    l.debug_p3 = True
    src = open(f'verilog/tests/normal/ref/{name}.v', encoding='utf-8').read()
    errs = l.scan(src)
    p3 = [x for x in errs if x.code == 'phase3-literal']
    print(f'\n{"="*60}')
    print(f'{name}: {len(p3)} P3 errors')
    for x in p3:
        print(f'  L{x.range[0].line}:{x.range[0].character} {x.message}')
    print(f'\nP3 Trace:')
    for t in l._p3_trace_log:
        if filter_fn is None or filter_fn(t):
            print(t)

# Pattern 1: port parens issues
trace('ref_simple_func', lambda t: any(
    kw in t for kw in ['PortParens', 'PortList', 'AnsiPort', 'AnsiInput',
                       'candidates i= 11', 'best i= 11', 'scan i= 11',
                       'candidates i= 37', 'best i= 37',
                       'candidates i= 43', 'best i= 43',
                       'token_err i= 12', 'token_err i= 13']
))
