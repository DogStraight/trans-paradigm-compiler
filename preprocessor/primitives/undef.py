"""undef — `undef NAME 指令处理器

Doc: preprocessor/README.md
"""

from .registry import register, split_directive


@register("undef")
def handle_undef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `undef NAME。

    **形参表状态一并清**（`_func_params`）：否则 `#define F(x)` → `#undef F` →
    `#define F 2` 后再 `F(3)` 仍被当函数宏（读不到形参就按"无参函数宏"处理），
    与 C 语义不符（`#undef` 后是普通对象宏 ⇒ `F(3)` → `2(3)`）。
    """
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析名字
    _keyword, arg = split_directive(stripped, prefix)
    name = arg.strip()
    ctx["macro_defs"].pop(name, None)
    func_params = ctx.get("_func_params")
    if isinstance(func_params, dict):
        func_params.pop(name, None)
