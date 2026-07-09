"""_invert_map.py — Verilog 方向反转映射

注册为 analyzer primitive，在 resolve_refs 之后运行，
为 _ref_callbacks 中的 invert 回调附加方向反转映射表。

作用：
    将 _analyzer.toml 的 [direction] invert_map 注入到回调中，
    使变换回调自描述（声明式），变换器无需再查配置即可执行反转。

回调输出格式：
    {
        "kind": "invert",
        "source_role": "master",
        "resolved_ports": [...],        # scope 查到的原始端口
        "invert_map": {                 # ← 由本原语附加
            "input": "output",
            "output": "input",
            ...
        }
    }
"""

from core.define import Node
from analyzer.primitives.registry import analyzer_primitive

# Verilog 方向反转映射表（语言专用数据）
_INVERT_MAP = {
    "input": "output",
    "output": "input",
    "input_reg": "output_reg",
    "output_reg": "input_reg",
    "inout": "inout",
}


@analyzer_primitive("attach_invert_map")
def attach_invert_map(analyzer, node: Node, config: dict) -> None:
    """为 _ref_callbacks 中的 invert 回调附加 invert_map

    在 TypeRole 的 analyzer 管线中，此原语应排在 resolve_refs 之后。
    它扫描当前符号的 _ref_callbacks，为 kind="invert" 的条目附加 invert_map。
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

    invert_map = _INVERT_MAP

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
