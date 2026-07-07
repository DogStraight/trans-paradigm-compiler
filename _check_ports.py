"""Check if PortList has 2 items at runtime"""
import sys
sys.path.insert(0, '.')
from verilog.run_pipeline import run_pipeline_on_source

source = open('verilog/tests/errors/ref/ref_error_garbage.v').read()
result = run_pipeline_on_source(source, global_recovery=True, quiet=True)
if result['ast']:
    def find_pl(node, path='root'):
        if hasattr(node, 'node_name') and node.node_name == 'PortList':
            items = getattr(node, 'items', [])
            print('PortList items: %d' % len(items))
            for i, item in enumerate(items):
                name = item.node_name if hasattr(item, 'node_name') else '?'
                print('  [%d] %s' % (i, name))
        for child in node.iter_children():
            find_pl(child, path)
    find_pl(result['ast'])
else:
    print('Error: %s' % result['error'])
