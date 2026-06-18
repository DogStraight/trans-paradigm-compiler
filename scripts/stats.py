import os

py_total = 0
toml_total = 0
by_dir = {}

for root, dirs, files in os.walk(r'e:\project\pyv_compiler'):
    # skip generated/irrelevant dirs
    skip = False
    for part in root.split(os.sep):
        if part in ('ref', 'gen', 'ast', 'symbols', '__pycache__', 'scripts', 'docs', '.git'):
            skip = True
            break
    if skip:
        continue

    for f in files:
        if not (f.endswith('.py') or f.endswith('.toml')):
            continue
        path = os.path.join(root, f)
        try:
            with open(path, encoding='utf-8') as fh:
                lines = len(fh.readlines())
        except:
            continue

        dirname = os.path.basename(os.path.dirname(path))
        if dirname not in by_dir:
            by_dir[dirname] = {'py': 0, 'toml': 0}

        if f.endswith('.py'):
            by_dir[dirname]['py'] += lines
            py_total += lines
        else:
            by_dir[dirname]['toml'] += lines
            toml_total += lines

print(f"{'Directory':20s} {'Python':>6s} {'TOML':>6s} {'Total':>6s}")
print("-" * 40)
for d in sorted(by_dir):
    v = by_dir[d]
    if v['py'] or v['toml']:
        print(f"{d:20s} {v['py']:6d} {v['toml']:6d} {v['py']+v['toml']:6d}")
print("-" * 40)
print(f"{'TOTAL':20s} {py_total:6d} {toml_total:6d} {py_total+toml_total:6d}")
print(f"\nPython/TOML ratio: {py_total}/{toml_total} = {py_total/toml_total:.2f}")
print(f"\n--- File list ---")

for root, dirs, files in os.walk(r'e:\project\pyv_compiler'):
    skip = False
    for part in root.split(os.sep):
        if part in ('ref', 'gen', 'ast', 'symbols', '__pycache__', 'scripts', 'docs', '.git'):
            skip = True
            break
    if skip:
        continue
    for f in sorted(files):
        if not (f.endswith('.py') or f.endswith('.toml')):
            continue
        path = os.path.join(root, f)
        try:
            with open(path, encoding='utf-8') as fh:
                lines = len(fh.readlines())
        except:
            continue
        rel = path.replace(r'e:\project\pyv_compiler\\', '')
        tag = 'py' if f.endswith('.py') else 'tm'
        print(f"  {tag} {lines:4d}  {rel}")
