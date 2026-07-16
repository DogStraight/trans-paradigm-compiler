"""Check remaining Chinese comments/docstrings."""
import os, re

def walk(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py'):
                yield os.path.join(dirpath, f)

targets = ['analyzer', 'renderer', 'normalizer', 'transform',
           'linter', 'scripts', 'verilog',
           'grammar/rules_verilog_ext']

count = 0
for td in targets:
    if not os.path.isdir(td):
        continue
    for path in walk(td):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'"""(.*?)"""', content, re.DOTALL):
            text = m.group(1)
            if re.search(r'[\u4e00-\u9fff]', text):
                print(f'{path}:')
                for line in text.strip().split('\n')[:5]:
                    print(f'  {line}')
                print()
                count += 1

print(f'Total: {count} Chinese docstrings remaining')
