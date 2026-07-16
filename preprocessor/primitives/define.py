"""define — `define NAME body 指令处理器"""

from .registry import register


@register("define")
def handle_define(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `define NAME body。"""
    arg = stripped[len(prefix) + len("define ") :]
    name_end = arg.find(" ")
    if name_end > 0:
        def_name = arg[:name_end]
        def_body = arg[name_end:].strip()
        ctx["macro_defs"][def_name] = def_body
    else:
        ctx["macro_defs"][arg] = ""
