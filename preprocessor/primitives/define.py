"""define — `define NAME body 指令处理器

Doc: docs/api.md（管线第一阶段：define 指令）
"""

import re

from .registry import register

_NAME_RE = re.compile(r"([A-Za-z_]\w*)")


@register("define")
def handle_define(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `define NAME body。

    支持两种形态：
      object-like:  `define NAME body          （名字后为空白或结束）
      function-like:`define NAME(a, b) body    （名字后紧跟 `(`，形参逗号分隔）
    function-like 的形参表写入 ctx["_func_params"]，body 存入 macro_defs。
    """
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析名字
    arg = stripped[len(prefix) + len("define ") :]
    m = _NAME_RE.match(arg)
    if not m:
        return
    def_name = m.group(1)
    rest = arg[m.end() :]

    if rest.startswith("("):
        # function-like：`define NAME(a, b) body
        close = rest.find(")")
        if close < 0:
            # 形参表未闭合（容错）：退化为 object-like
            ctx["macro_defs"][def_name] = rest.strip()
            return
        params = [p.strip() for p in rest[1:close].split(",") if p.strip()]
        body = rest[close + 1 :].strip()
        ctx["macro_defs"][def_name] = body
        ctx.setdefault("_func_params", {})[def_name] = params
    else:
        ctx["macro_defs"][def_name] = rest.strip()
