"""define — `define NAME body 指令处理器

形参表形态（括号对 / 分隔符）来自语言包 `[macro_recognition]` 的 `call_args` /
`arg_separator` 声明（经 scan_directives 放入 ctx，见
`preprocessor/macro_shape.py::load_macro_call_args`）——定义侧与调用侧同形，
引擎不硬编码 `(` / `,`。

Doc: preprocessor/README.md
"""

import re

from .registry import register, split_directive

_NAME_RE = re.compile(r"([A-Za-z_]\w*)")


@register("define")
def handle_define(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `define NAME body。

    支持两种形态：
      object-like:  `define NAME body          （名字后为空白或结束）
      function-like:`define NAME(a, b) body    （名字后紧跟开括号，形参按声明分隔）
    function-like 的形参表写入 ctx["_func_params"]，body 存入 macro_defs。
    关键字/前缀不写死：参数区由 `split_directive` 切出（前缀 + 关键字 + 空白）。
    """
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析名字
    _keyword, arg = split_directive(stripped, prefix)
    m = _NAME_RE.match(arg)
    if not m:
        return
    def_name = m.group(1)
    rest = arg[m.end() :]

    call_args = ctx.get("_call_args")
    if call_args is not None and rest.startswith(call_args.open):
        # function-like：`define NAME(a, b) body
        matched = call_args.match_args(rest, 0)
        if matched is None:
            # 形参表未闭合（容错）：退化为 object-like
            ctx["macro_defs"][def_name] = rest.strip()
            return
        params_text, body_idx = matched
        params = [p for p in call_args.split(params_text) if p]
        ctx["macro_defs"][def_name] = rest[body_idx:].strip()
        ctx.setdefault("_func_params", {})[def_name] = params
    else:
        ctx["macro_defs"][def_name] = rest.strip()
