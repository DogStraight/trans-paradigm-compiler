"""_mapping.py — Verilog semantic mapping table definitions.

Defines how analyzer symbol attrs map to transformer mapping tables.
Consumed by SemanticMappingPlugin (first stage of transform pipeline).

This file is the typed_ports component's language config entry point.
"""

from core._protocol import TABLE_TYPE_PORTS_FLAT

# ── Language info ──
LANG = "verilog"

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
        # 端口位宽（packed_range）随行携带：emit 端按 ref 透传重建 Range 节点。
        # 捕获数据缺 packed_range 键的端口（无位宽）该字段被跳过，行内不出现。
        "packed_range": "{$.packed_range}",
    },
}

mapping_entries: dict = {
    TABLE_TYPE_PORTS_FLAT: _type_ports_flat,
}

# resolve_entries（apply_refs 后处理）与 collect_callbacks（trans_callback dump）
# 已随旧 analyze 原语链删除（P1.5 step 2）——role 端口展开现由 _expand_ports
# postpass 写 resolved_ports，SemanticMappingPlugin._apply_entry 直接注入。
