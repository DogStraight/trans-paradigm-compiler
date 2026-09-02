"""undef — `undef NAME 指令处理器

Doc: docs/api.md（管线第一阶段：undef 指令）
"""

from .registry import register


@register("undef")
def handle_undef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `undef NAME。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析名字
    arg = stripped[len(prefix) + len("undef ") :].strip()
    ctx["macro_defs"].pop(arg, None)
