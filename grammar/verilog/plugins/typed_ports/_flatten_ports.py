"""
_flatten_ports.py — 端口数据拍平原语

注册为 analyzer primitive，在 resolve_refs 之后运行，
将 _ref_callbacks 中 resolved_ports 的嵌套结构拍平为 {direction, name} 格式。

语言专用数据由 TOML 配置驱动，引擎本身不含语言知识。
"""

from core.define import Node
from analyzer.primitives.registry import register


@register("flatten_ports")
def flatten_ports(analyzer, node: Node, config: dict) -> None:
    """遍历 _ref_callbacks，拍平 resolved_ports 中的嵌套端口结构。

    TOML 配置：
        [RuleName.analyzer.flatten_ports]
        direction = "{$.direction}"
        name = "items.items[*].name"

    未配置时不处理（向下兼容）。
    """
    self_cfg = config.get("flatten_ports", {})
    dir_spec = self_cfg.get("direction", "")
    name_spec = self_cfg.get("name", "")
    if not dir_spec and not name_spec:
        return

    scope = analyzer._current_scope
    if scope is None:
        return

    _flatten_all_callbacks(scope, dir_spec, name_spec)


def _flatten_all_callbacks(scope, dir_spec: str, name_spec: str) -> None:
    """递归遍历 scope 树，拍平所有符号的 _ref_callbacks。"""
    for sym in scope.symbols.values():
        callbacks = sym.attrs.get("_ref_callbacks", [])
        if not isinstance(callbacks, list):
            continue
        modified = False
        for cb in callbacks:
            ports = cb.get("resolved_ports", [])
            if not isinstance(ports, list):
                continue
            flat = _flatten_one(ports, dir_spec, name_spec)
            if flat != ports:
                cb["resolved_ports"] = flat
                modified = True
        if modified:
            sym.attrs["_ref_callbacks"] = callbacks

    for child in scope.children:
        _flatten_all_callbacks(child, dir_spec, name_spec)


def _flatten_one(ports: list, dir_spec: str, name_spec: str) -> list:
    """将单个端口列表从嵌套结构拍平为 {direction, name}，携带 packed_range。"""
    result = []
    for port in ports:
        if not isinstance(port, dict):
            result.append(port)
            continue

        direction = ""
        if dir_spec.startswith("{$.") and dir_spec.endswith("}"):
            direction = port.get(dir_spec[3:-1], "")

        names: list = []
        if "[*]" in name_spec:
            val = port
            for part in name_spec.replace("[*]", "").split("."):
                part = part.strip()
                if isinstance(val, dict):
                    val = val.get(part, {})
                elif isinstance(val, list):
                    collected = []
                    for v in val:
                        if isinstance(v, dict):
                            n = v.get(part, "")
                            if n:
                                collected.append(n)
                        elif isinstance(v, str):
                            collected.append(v)
                    val = collected
                else:
                    val = {}
            names = val if isinstance(val, list) else []
        else:
            names = [port.get(name_spec, "")] if name_spec else []

        # 位宽（packed_range）随行携带：源数据缺该键（无位宽端口）时不设置，
        # emit 端 ref 透传缺失时按"无此属性"处理，渲染端 opt 跳过。
        def _entry(direction: str, name: str) -> dict:
            entry: dict = {"direction": direction, "name": name}
            pr = port.get("packed_range") if isinstance(port, dict) else None
            if pr:
                entry["packed_range"] = pr
            return entry

        if not names:
            result.append(_entry(direction, port.get("name", "")))
        else:
            for n in names:
                result.append(
                    _entry(direction, n) if isinstance(n, str) else _entry(direction, "")
                )
    return result
