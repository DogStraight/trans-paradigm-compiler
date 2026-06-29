from .scope import Scope, Symbol, get_symbol_kinds
from .semantic_analyzer import SemanticAnalyzer, register_capture_hook


# ── 内置 capture 后处理器 ──

@register_capture_hook("resolve_revert")
def _resolve_revert(node, sym_rule, scope, name, attrs):
    """解析角色中的 revert 声明：查目标角色端口并反转方向。"""
    def _rev(d):
        return "output" if d in ("input", "input_reg") else "input" if d in ("output", "output_reg") else d

    ports = attrs.get("ports")
    if not ports:
        return attrs
    if not isinstance(ports, list):
        ports = [ports]
    resolved = []
    for port in ports:
        if not isinstance(port, dict):
            resolved.append(port)
            continue
        if port.get("node_name") == "TypeRevertPort":
            target = port.get("target_role", "")
            if target and target in scope.symbols:
                for tp in (scope.symbols[target].attrs.get("ports") or []):
                    if not isinstance(tp, dict) or not tp.get("direction"):
                        continue
                    rev = dict(tp)
                    rev["direction"] = _rev(tp["direction"])
                    resolved.append(rev)
        else:
            resolved.append(port)
    attrs["ports"] = resolved if len(resolved) != 1 else resolved[0]
    return attrs


__all__ = ["Scope", "Symbol", "get_symbol_kinds", "SemanticAnalyzer", "register_capture_hook"]
