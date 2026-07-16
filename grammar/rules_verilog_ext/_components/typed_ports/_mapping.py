"""_mapping.py — Verilog 语义映射表定义

定义分析器符号 attrs → 变换器映射表的转换规则。
消费方：SemanticMappingPlugin（transform 管线第一阶段）

本文件是 typed_ports 组件的语言配置入口。
"""

# ── 语言配置（由管线消费）──
LANG = "verilog"
RULES_DIR = "grammar/rules_verilog"
EXT_DIRS = ["grammar/rules_verilog_ext"]
# 端口表：从 role 符号的 attrs["ports"] 提取 direction + name
_type_ports_flat = {
    "trigger": {"kind": "role"},
    "table": "type_ports_flat",
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

# 变换回调消费
_apply_refs = {
    "kind": "apply_refs",
}

mapping_entries: dict = {
    "type_ports_flat": _type_ports_flat,
}

resolve_entries: dict = {
    "apply_type_refs": _apply_refs,
}


def collect_callbacks(scope) -> dict:
    """递归收集 scope 树中所有符号的 _ref_callbacks

    输出文件格式（trans_callback/{name}.json）：
        { "type_name.role_name": [{ "kind": "nested|invert", ... }] }
    """
    result: dict = {}

    def _walk(s):
        for sym in s.symbols.values():
            cbs = sym.attrs.get("_ref_callbacks", [])
            if cbs:
                result[f"{s.name}.{sym.name}"] = cbs
        for child in s.children:
            _walk(child)

    _walk(scope)
    return result

resolve_entries: dict = {
    "apply_type_refs": _apply_refs,
}
