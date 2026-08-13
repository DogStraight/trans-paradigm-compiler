# Config Loading Convention

## Three-tier Architecture

```
pyv.toml                    Data TOML files              Python consumer
┌─────────────────┐        ┌──────────────────┐         ┌──────────────────┐
│ [config.xxx]    │──file→ │ [section]         │──→     │ _xxx_cfg: dict   │
│   key_name      │  section│ key = value       │  config.get()│                 │
│   file="..."    │  (#sym)│ ...               │         │ def func():      │
│   section=".."  │        └──────────────────┘         │   return _xxx_cfg│
└─────────────────┘                                      └──────────────────┘
```

### Tier 1: `pyv.toml` — Declaration + Addressing

```toml
[config.preprocessor]
expand = { file = "base/_macro.toml", section = "expand", required = false }
```

- `[config.<namespace>]` — which component needs config
- `key_name` — config interface name
- `file` — relative path within the grammar package
- `section` — `#sym:config`, the TOML section within the file that holds the data
- `required` — whether failure to load is fatal

### Tier 2: Data TOML File — Actual Config Values

```toml
[expand]
max_iterations = 128
```

Pure data, no logic. The `section` field in pyv.toml (`#sym:config`) points here.

### Tier 3: Python Consumer — Module-level Variable + Thin Wrapper

```python
from core.config_registry import config

# <config_key>
#   #sym:config = [section]
#   格式: dict — { field: type, description }
_xxx_cfg: dict = {default_value}
try:
    _xxx_cfg = dict(config.get("namespace.key"))
except (KeyError, RuntimeError):
    pass

def getter() -> dict:
    return _xxx_cfg
```

Convention rules:
- Variable name: `_<short>_cfg` (lowercase, underscore prefix, `_cfg` suffix)
- Type annotation: `dict` (not `dict | None`)
- Default value set directly at declaration (not `None`)
- `except` uses `pass` — default already in place
- Getter function is a thin `return` with no logic
- `config.get()` called exactly once at module level

## Reflection: Package-internal `get_config_refs()`

Each package exposes `get_config_refs()` that scans its submodules for `_*_cfg` variables:

```python
from preprocessor import get_config_refs
refs = get_config_refs()
# → { "preprocessor.expand": "_expand_cfg",
#     "preprocessor.directives": "_directives_cfg",
#     "preprocessor.reverse": "_reverse_cfg",
#     "preprocessor.macro_config": "_macro_cfg" }
```

### Shared regex

`core/config_registry.py` exports two regex pattern strings for reuse across packages:

```python
from core.config_registry import CFG_VAR_PATTERN, CFG_GET_PATTERN

_VAR_RE = re.compile(CFG_VAR_PATTERN)
_GET_RE = re.compile(CFG_GET_PATTERN)
```

### Package-level implementation

Each `__init__.py` uses the shared patterns to scan submodules:

```python
import inspect, re
from core.config_registry import CFG_VAR_PATTERN, CFG_GET_PATTERN

_VAR_RE = re.compile(CFG_VAR_PATTERN)
_GET_RE = re.compile(CFG_GET_PATTERN)

def get_config_refs() -> dict[str, str]:
    refs = {}
    for mod in (_sub_a, _sub_b):
        try:
            source = inspect.getsource(mod)
        except (OSError, TypeError):
            continue
        lines = source.split("\n")
        for i, line in enumerate(lines):
            m = _VAR_RE.match(line.strip())
            if not m:
                continue
            # In nearby lines, find config.get("key")
            ...
    return refs
```

### Generating pyv.toml entries

```python
from preprocessor import get_config_refs

for key, var in get_config_refs().items():
    ns, name = key.rsplit(".", 1)
    print(f"[config.{ns}]")
    print(f'{name} = {{ file = "...", section = "...", required = false }}')
```

### Convention summary

| Element | Convention | Example |
|---------|-----------|---------|
| Module var | `_<short>_cfg: dict` | `_expand_cfg: dict` |
| Default | Direct assignment | `= {"max_iterations": 128}` |
| Config load | `dict(config.get("key"))` in try | `config.get("preprocessor.expand")` |
| Exception | `pass` (default already set) | `except: pass` |
| Getter | Thin `return var` | `return _expand_cfg` |
| Registration | `scan_config_refs()` auto-detects | via regex on source |
