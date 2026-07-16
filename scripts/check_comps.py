"""Check components."""
import sys; sys.path.insert(0, '.')
from core.component_loader import load_all_components, get_loaded_components
load_all_components()
for name, info in get_loaded_components().items():
    print(f'Component: {name}')
    trans = info.get('transform', [])
    print(f'  transform handlers: {len(trans)}')
    for m in trans:
        print(f'    {getattr(m, "__name__", "?")}')
from transform.pipeline import _plugin_registry
print('Registered plugins:', [p.__name__ for p in _plugin_registry])
