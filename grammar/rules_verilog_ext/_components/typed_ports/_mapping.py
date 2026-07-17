"""_mapping.py — Verilog semantic mapping table definitions.

Defines how analyzer symbol attrs map to transformer mapping tables.
Consumed by SemanticMappingPlugin (first stage of transform pipeline).

This file is the typed_ports component's language config entry point.
"""

from grammar.rules_verilog_ext._components._protocol import (
    TABLE_TYPE_PORTS_FLAT,
    ATTR_REF_CALLBACKS,
)

# ── Language config (consumed by pipeline) ──
LANG = "verilog"
RULES_DIR = "grammar/rules_verilog"
EXT_DIRS = ["grammar/rules_verilog_ext"]

# Port mapping: extract direction + name from role symbol attrs["ports"]
_type_ports_flat = {
    "trigger": {"kind": "role"},
    "table": TABLE_TYPE_PORTS_FLAT,
    "key": "{scope.name}.{name}",
    "source": {
        "attr": "ports",
        "items": True,
        "exclude_keys": ["type_spec", "target_role"],
    },
    "fields": {
        "direction": "{$.direction}",
        "name": "items.items[*].name",
    },
}

# Transform callback consumer
_apply_refs = {"kind": "apply_refs"}

mapping_entries: dict = {
    TABLE_TYPE_PORTS_FLAT: _type_ports_flat,
}

resolve_entries: dict = {
    "apply_type_refs": _apply_refs,
}


def collect_callbacks(scope) -> dict:
    """Recursively collect _ref_callbacks from all symbols in the scope tree.

    Output format (trans_callback/{name}.json):
        { "type_name.role_name": [{ "kind": "nested|invert", ... }] }
    """
    result: dict = {}

    def _walk(s):
        for sym in s.symbols.values():
            cbs = sym.attrs.get(ATTR_REF_CALLBACKS, [])
            if cbs:
                result[f"{s.name}.{sym.name}"] = cbs
        for child in s.children:
            _walk(child)

    _walk(scope)
    return result
