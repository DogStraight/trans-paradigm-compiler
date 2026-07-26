"""Rewrite rule definitions to use block.start/end, remove intermediate blocks."""
import os, tomllib, tomli_w

D = r'E:\project\pyv_compiler\grammar\verilog'

# ── 规则转换配置 ──
# (toml_path, rule_name, block_start, block_end,
#  new_production, body_renderer, extra_structure)
transforms = [
    # ModuleDecl
    ('01_module.toml', 'ModuleDecl',
     'keyword.module', 'keyword.endmodule',
     ['@Identifier', '@ParameterList?', '@PortParens?', 'symbol.base.semicolon?'],
     {'indent': True, 'role': 'flatten'},
     None),

    # FuncDeclANSI
    ('04_statements/50_func_task.toml', 'FuncDeclANSI',
     'keyword.function', 'keyword.endfunction',
     ['(keyword.automatic|keyword.static)?', 'keyword.signed?', '@Range?',
      '@Identifier', 'bracket.l_parentheses', '@TaskPortList?', 'bracket.r_parentheses',
      'symbol.base.semicolon'],
     {'indent': True, 'role': 'flatten'},
     None),

    # FuncDeclOld
    ('04_statements/50_func_task.toml', 'FuncDeclOld',
     'keyword.function', 'keyword.endfunction',
     ['(keyword.automatic|keyword.static)?', 'keyword.signed?',
      '@Range?', '@Identifier', 'symbol.base.semicolon'],
     {'indent': True, 'role': 'flatten'},
     None),

    # TaskDeclANSI
    ('04_statements/50_func_task.toml', 'TaskDeclANSI',
     'keyword.task', 'keyword.endtask',
     ['(keyword.automatic|keyword.static)?', '@Identifier',
      'bracket.l_parentheses', '@TaskPortList?', 'bracket.r_parentheses',
      'symbol.base.semicolon'],
     {'indent': True, 'role': 'flatten'},
     None),

    # TaskDeclOld
    ('04_statements/50_func_task.toml', 'TaskDeclOld',
     'keyword.task', 'keyword.endtask',
     ['(keyword.automatic|keyword.static)?', '@Identifier',
      'symbol.base.semicolon'],
     {'indent': True, 'role': 'flatten'},
     None),

    # GenerateBlock
    ('04_statements/70_misc.toml', 'GenerateBlock',
     'keyword.generate', 'keyword.endgenerate',
     [],
     {'indent': True, 'role': 'flatten'},
     None),
]

for rel, name, bs, be, prod, body_render, extra_struct in transforms:
    fp = os.path.join(D, rel)
    with open(fp, 'rb') as f:
        data = tomllib.load(f)

    rule = data[name]
    parser = rule.get('parser', {})

    # Update structure
    rule['structure'] = {'is_block': True, 'is_statement': True}

    # Add block.start/end
    rule['block'] = {'start': bs, 'end': be}

    # Update production (remove end keyword and @Block calls)
    parser['production'] = prod

    # Update end_case
    parser['end_case'] = [be, 'newline']

    # Add body renderer (was on the removed @Block rule)
    renderer = rule.setdefault('renderer', {})
    renderer['body'] = body_render

    # Remove old node references to @Block
    node = parser.get('node', {})
    # body was from $N referencing @Block, now it's implicit
    # Keep only non-body attrs
    if 'body' in node:
        del node['body']

    with open(fp, 'wb') as f:
        tomli_w.dump(data, f)
    print(f'  UPDATED: {rel} / {name}')
    print(f'    block: {bs} / {be}')
    print(f'    production: {prod}')

print('\nDone')
