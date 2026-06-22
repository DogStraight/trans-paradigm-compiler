"""添加括号 layout 到表达式语法文件"""
with open('grammar/rules_verilog/05_expressions.toml', 'a', encoding='utf-8') as f:
    f.write('\n')
    f.write('# 括号节点渲染（被 seq 保留为 Node，需要 layout 才能显示）\n')
    f.write('["bracket.l_square_bracket"]\n')
    f.write('renderer = { layout = { ref = "value" } }\n')
    f.write('["bracket.r_square_bracket"]\n')
    f.write('renderer = { layout = { ref = "value" } }\n')
