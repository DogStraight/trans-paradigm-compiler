import os, tomllib
fp = r'E:\project\pyv_compiler\grammar\verilog\00_blocks.toml'
with open(fp, 'rb') as f:
    data = tomllib.load(f)
for name in ['ModuleBlock','ProcBlock','TaskBlock']:
    if name in data:
        rd = data[name]
        p = rd.get('parser', {})
        print(name + ':')
        print('  structure:', rd.get('structure'))
        print('  production:', p.get('production'))
        print('  end_case:', p.get('end_case'))
        print('  renderer:', rd.get('renderer'))
        print()
