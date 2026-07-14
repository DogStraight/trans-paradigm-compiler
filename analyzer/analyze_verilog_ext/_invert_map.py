"""_invert_map.py — 方向反转映射原语

注册为 analyzer primitive，在 resolve_refs 之后运行，
为 _ref_callbacks 中的 invert 回调附加方向反转映射表。

映射表由调用侧通过 TOML 配置传入（`analyzer.invert_map`），
引擎本身不包含任何语言专用方向数据。

回调输出格式：
    {
        "kind": "invert",
        "source_role": "master",
        "resolved_ports": [...],
        "invert_map": {                 # ← 由本原语从 config 读取
            "input": "output",
            "output": "input",
            ...
        }
    }
"""

from core.define import Node
from analyzer.primitives.registry import register


@register("attach_invert_map")
def attach_invert_map(analyzer, node: Node, config: dict) -> None:
    """为 _ref_callbacks 中的 invert 回调附加 invert_map

    从 config 参数读取 invert_map，而非硬编码。
    语言专用数据由调用侧的 TOML analyzer.invert_map 提供。
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

    # 为 invert 回调附加 invert_map
    modified = False
    for cb in callbacks:
        if cb.get("kind") == "invert" and "invert_map" not in cb:
            cb["invert_map"] = dict(invert_map)
            modified = True

    if modified:
        sym.attrs["_ref_callbacks"] = callbacks
