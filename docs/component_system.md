# Component System

Components are self-contained units that extend TransParadigm's capabilities for a specific language feature. Each component bundles:

- **Grammar rules** (TOML) — syntax definitions for the feature
- **Analyzer primitives** (Python) — semantic analysis during AST traversal
- **Transform slots** (Python) — post-phase AST modification
- **Mapping config** (Python) — how symbol attrs map to transformer tables

## Directory Structure

```
grammar/rules_verilog_ext/_components/
├── _protocol.py            # Shared constants (magic string centralization)
├── builtins/               # Cross-language analyzer primitives
│   ├── component.toml      # Component manifest
│   ├── _scope.py           # scope_enter / scope_exit primitives
│   ├── _symbol.py          # symbol_declare primitive
│   ├── _identifier.py      # identifier_resolve primitive
│   ├── _resolve.py         # resolve_refs primitive
│   └── _semantic_mapping.py # SemanticMappingPlugin transform
├── typed_ports/            # Verilog typed port system
│   ├── component.toml
│   ├── 00_type_decl.toml   # TypeDecl, TypeRole, TypeImplDecl grammar
│   ├── 06_typed_decl.toml  # TypedTypeSpec, TypedPortDecl grammar
│   ├── 10_impl_binding.toml# ImplBinding, ImplBindingWithInterface grammar
│   ├── _mapping.py         # Language config entry point
│   ├── _bridge.py          # ComponentSlotPlugin (transform orchestrator)
│   ├── _transform.py       # Transform slots (build_wrapper, etc.)
│   ├── _flatten_ports.py   # flatten_ports analyzer primitive
│   └── _invert_map.py      # attach_invert_map analyzer primitive
└── <your_component>/       # Your component here
```

## `component.toml` Reference

```toml
[component]
name = "my_feature"           # Component name (snake_case)
lang = "verilog"              # Target language, "*" for cross-language
description = "..."           # Short description
requires = ["builtins"]       # Dependencies (loaded in order)

[component.grammar]
files = ["00_my_feature.toml"]  # Grammar TOML files (relative to component dir)

[component.analyzer]
primitive_order = ["prim_a", "prim_b"]  # Execution order
primitives = ["prim_a", "prim_b"]        # Declared primitive names
handlers = ["_my_handler.py"]            # Python handler files

[component.transform]
slots = ["slot_name"]                    # Transform slot names
handlers = ["_my_transform.py"]          # Transform handler files
```

## Creating a New Component

```bash
python main.py new component my_feature --lang verilog
```

This scaffolds:

```
_components/my_feature/
├── component.toml      # Manifest (edit name/lang/requires/files)
├── 00_my_feature.toml  # Grammar rules (edit productions)
└── _my_feature.py      # Python handler (edit the process function)
```

## Data Flow

```
TOML grammar rules
      ↓ (loaded by setup_grammar)
Parser produces AST
      ↓
Analyzer traverses AST, executes component primitives
      ↓ (primitives write to sym.attrs via _protocol keys)
SemanticMappingPlugin reads scope tree, builds mapping table
      ↓ (table: "type_ports_flat" etc.)
ConfigDrivenTransform consumes mapping table
      ↓ (expand / replace / delete operations)
Renderer produces formatted output
```

### The `_ref_callbacks` Protocol

The key data channel between analyzer and transformer:

1. **Analyzer** (`_resolve.py`): puts callbacks in `sym.attrs["_ref_callbacks"]`
2. **Collector** (`_mapping.py`): `collect_callbacks()` reads them from scope tree
3. **Transformer** (`_semantic_mapping.py`): builds mapping table from callbacks

All such keys are documented in `_protocol.py`. Never use raw strings.

## Best Practices

1. **One component, one feature** — don't bundle unrelated logic
2. **Declare dependencies** — `requires = ["builtins"]` for analyzer primitives
3. **Use `_protocol.py` constants** — never hardcode `"_ref_callbacks"` etc.
4. **Test with `run_all_tests.py`** — component changes must pass full regression
