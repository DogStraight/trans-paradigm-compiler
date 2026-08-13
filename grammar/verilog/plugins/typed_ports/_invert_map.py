"""_invert_map.py — 方向反转映射原语

注册为 analyzer primitive，在 resolve_refs 之后运行，
就地反转 _ref_callbacks 中 invert 回调的 resolved_ports 方向。

反转由 TOML 配置传入（`analyzer.invert_map`），引擎本身不含语言专用数据。
变换器不再感知 invert_map——它只看到已经反转好的扁平端口。

本文件使用的配置（来自 pyv.toml 中 typed_ports 组件的 analyzer 声明）:
    invert_map: dict — 端口方向反转映射
        { "direction_name": "reversed_direction", ... }
        例: { "input": "output", "output": "input" }
    attach_invert_map: dict — 同 invert_map 的外层包装（兼容嵌套写法）
        { "invert_map": { ... }, "other_meta": ... }
"""

from core.define import Node
from analyzer.primitives.registry import register


@register("attach_invert_map")
def attach_invert_map(analyzer, node: Node, config: dict) -> None:
    """为 _ref_callbacks 中的 invert 回调就地反转 resolved_ports

    从 config 读取 invert_map，直接反转 resolved_ports 中的 direction 字段。
    变换器不再感知 invert_map 的存在——它只看到已经反转好的端口数据。
    语言专用数据由 TOML analyzer.invert_map 提供。
    """
    role_name = getattr(node, "role_name", None)
    if role_name is None:
        return
    if isinstance(role_name, Node):
        role_name = getattr(role_name, "content", None)
    if not role_name:
        return

    scope = analyzer._current_scope
    if scope is None:
        return
    sym = scope.resolve(role_name)
    if sym is None:
        return

    callbacks = sym.attrs.get("_ref_callbacks", [])
    if not callbacks:
        return

    invert_map = config.get("invert_map", {})

    # 兼容嵌套写法：analyzer.attach_invert_map = { invert_map = {...} }
    if not invert_map:
        prim_cfg = config.get("attach_invert_map", {})
        if isinstance(prim_cfg, dict):
            invert_map = prim_cfg.get("invert_map", {})

    if not invert_map:
        return

    # 就地反转 invert 回调的 resolved_ports
    modified = False
    for cb in callbacks:
        if cb.get("kind") != "invert":
            continue
        ports = cb.get("resolved_ports", [])
        if not ports:
            continue
        for port in ports:
            if "direction" in port:
                original = port["direction"]
                port["direction"] = invert_map.get(original, original)
        modified = True

    if modified:
        sym.attrs["_ref_callbacks"] = callbacks
