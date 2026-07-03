import sys, json; sys.path.insert(0,'verilog'); sys.path.insert(0,'.')
from core.define import GrammarRulesRegister
reg = GrammarRulesRegister.get_default()
reg._loaded_dirs.clear(); reg.rules.clear()
import run_pipeline as rp
rp._PIPELINE_SHARED.clear()
from run_pipeline import run_pipeline_on_source

for label, path in [
    ('syntax_err', 'tests/errors/ref/ref_syntax_err.v'),
]:
    src = open(f'verilog/{path}', encoding='utf-8').read()
    r = run_pipeline_on_source(src, quiet=True)
    dump = r['ast'].dump() if r['ast'] else None
    print(f'=== {label} ===')
    print(json.dumps(dump, indent=2, ensure_ascii=False)[:800])
    print()
    print(r['output'][:500])
