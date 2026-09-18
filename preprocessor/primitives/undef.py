"""undef — `undef NAME 指令处理器

Doc: preprocessor/README.md
"""

from .registry import register, split_directive


@register("undef")
def handle_undef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `undef NAME。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析名字
    _keyword, arg = split_directive(stripped, prefix)
    ctx["macro_defs"].pop(arg.strip(), None)
