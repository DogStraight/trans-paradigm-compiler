"""Move template from after [Rule.node] to before it in TOML files"""
import os, re

rules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'grammar', 'rules_verilog')

for fname in sorted(os.listdir(rules_dir)):
    if not fname.endswith('.toml'):
        continue
    fpath = os.path.join(rules_dir, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for [X.node] header
        m = re.match(r'^(\[[\w.]+\.node\])\s*$', line)
        if m:
            node_header = m.group(1)
            # Collect content after [X.node] until next section
            after = []
            i += 1
            while i < len(lines) and not lines[i].startswith('['):
                after.append(lines[i])
                i += 1

            # Find template in after
            t_start = -1
            for k, al in enumerate(after):
                if al.strip().startswith('template ='):
                    t_start = k
                    break

            if t_start >= 0:
                # Collect template lines
                tlines = [after[t_start]]
                if '"""' in after[t_start]:
                    k = t_start + 1
                    while k < len(after) and '"""' not in after[k]:
                        tlines.append(after[k])
                        k += 1
                    if k < len(after):
                        tlines.append(after[k])
                        k += 1
                else:
                    k = t_start + 1

                # Remaining lines (without template)
                remaining = after[:t_start] + after[k:]
                # Output: template, blank line, [X.node], remaining
                result.extend(tlines)
                if tlines and not tlines[-1].endswith('\n\n'):
                    result.append('\n')
                result.append(node_header + '\n')
                result.extend(remaining)
            else:
                result.append(node_header + '\n')
                result.extend(after)
        else:
            result.append(line)
            i += 1

    with open(fpath, 'w', encoding='utf-8') as f:
        f.writelines(result)
    print(f'Fixed: {fname}')
