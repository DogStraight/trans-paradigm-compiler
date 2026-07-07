"""Debug: trace PortList repeat loop - why is rstn not matched?"""
import sys; sys.path.insert(0, '.')
from parser.parser_core import Parser
from parser.node_parsers import repeat_loop as original_repeat_loop

def traced_repeat_loop(self, elem, context, min_count=0, max_count=None):
    result = original_repeat_loop(self, elem, context, min_count, max_count)
    # Only trace PortList context
    if context.current_node and context.current_node.node_name == 'PortList':
        t = context.peek_token(offset=-1)
        print('  [repeat_loop] PortList: min=%d result=%s nodes=%d last_token=%s' % (
            min_count, 
            'ok' if result is not None else 'None', 
            len(result) if result else 0,
            t.content if t else '?' 
        ))
        if result:
            for i, n in enumerate(result):
                if n and hasattr(n, 'node_name'):
                    print('    node[%d]: %s' % (i, n.node_name))
                    if n.node_name == 'seq' and hasattr(n, 'sub_node'):
                        for j, sn in enumerate(n.sub_node):
                            snn = sn.node_name if hasattr(sn, 'node_name') else '?'
                            print('      sub[%d]: %s' % (j, snn))
    return result

Parser._repeat_loop = traced_repeat_loop

from verilog.run_pipeline import run_pipeline_on_source
src = open('verilog/tests/errors/ref/ref_error_garbage.v').read()
r = run_pipeline_on_source(src, global_recovery=True, quiet=True, analyzer_enabled=False, transform_enabled=False)
