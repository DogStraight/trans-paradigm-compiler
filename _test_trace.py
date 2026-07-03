import sys; sys.path.insert(0,'verilog'); sys.path.insert(0,'.')
from core.define import GrammarRulesRegister
reg = GrammarRulesRegister.get_default()
reg._loaded_dirs.clear(); reg.rules.clear()
import run_pipeline as rp
rp._PIPELINE_SHARED.clear()

# Patch _try_production to trace stop_types
import parser.rule_matcher as rm
_orig = rm._try_production
def _traced(self, ctx, prod, rule, committed, sync_tokens=None):
    from core.define import GrammarRule
    if rule.name == 'ModuleDecl' and prod == '@PortParens?':
        st = set()
        for ec in getattr(rule, "end_case", []):
            if isinstance(ec, str) and not ec.startswith("!"):
                st.add(ec)
        if sync_tokens:
            st.update(sync_tokens)
        sys.stderr.write(f'  [trace] ModuleDecl {prod}: sync_tokens={sync_tokens} stop_types={st}\n')
    return _orig(self, ctx, prod, rule, committed, sync_tokens=sync_tokens)
rm._try_production = _traced

from run_pipeline import run_pipeline_on_source
src = open('verilog/tests/errors/ref/ref_syntax_err.v', encoding='utf-8').read()
r = run_pipeline_on_source(src, quiet=True)
print(r['output'][:300])
