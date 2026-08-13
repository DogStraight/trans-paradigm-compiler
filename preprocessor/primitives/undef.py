"""undef — `undef NAME 指令处理器"""

from .registry import register


@register("undef")
def handle_undef(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `undef NAME。"""
    arg = stripped[len(prefix) + len("undef ") :].strip()
    ctx["macro_defs"].pop(arg, None)
