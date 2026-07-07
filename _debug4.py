"""Deep trace: count repeat_loop iterations for PortList"""
import sys; sys.path.insert(0, '.')
import parser.node_parsers as np
_orig_rl = np.repeat_loop

def _trace_rl(self, elem, context, min_count=0, max_count=None):
    cn = context.current_node
    cn_name = cn.node_name if cn else '?'
    if cn_name == 'PortList':
        print('=== repeat_loop START (min=%d, max=%s) ===' % (min_count, max_count))
    result = _orig_rl(self, elem, context, min_count, max_count)
    if cn_name == 'PortList':
        print('=== repeat_loop END: count=%d ===' % (len(result) if result else 0))
    return result
np.repeat_loop = _trace_rl

# Also trace parse_seq
_orig_seq = np.parse_seq
def _trace_seq(self, node, context):
    cn = context.current_node
    cn_name = cn.node_name if cn else '?'
    result = _orig_seq(self, node, context)
    if cn_name == 'PortList' and result is not None:
        sub = getattr(result, 'sub_node', [])
        print('  seq matched: %d sub_nodes, next token idx=%d' % (len(sub), context.token_pointer))
    elif cn_name == 'PortList':
        print('  seq FAILED at token idx=%d' % context.token_pointer)
    return result
np.parse_seq = _trace_seq

from verilog.run_pipeline import run_pipeline_on_source
src = open('verilog/tests/errors/ref/ref_error_garbage.v').read()
r = run_pipeline_on_source(src, global_recovery=True, quiet=True, analyzer_enabled=False, transform_enabled=False)
