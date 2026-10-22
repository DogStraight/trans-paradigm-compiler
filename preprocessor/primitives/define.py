"""define — `define NAME body 指令处理器

形参表形态（括号对 / 分隔符）来自语言包 `[macro_recognition]` 的 `call_args` /
`arg_separator` 声明（经 scan_directives 放入 ctx，见
`preprocessor/macro_shape.py::load_macro_call_args`）——定义侧与调用侧同形，
引擎不硬编码 `(` / `,`。

**未闭合的形参表 ⇒ fail-fast**（`ConfigError`）：此前"容错退化为对象宏"会把
`#define F(a, b` 这类错误源静默当成对象宏（宏体带括号文本），与"声明错误不静默
降级"的纪律相悖。变参形态 `#define F(a, ...)` 的 `...` **不进形参表**（展开侧按
"超出具名形参的实参"绑定，见 `preprocessor/macro_expand.py`）。

Doc: preprocessor/README.md
"""

import re

from core.errors import ConfigError

from .registry import register, split_directive

_NAME_RE = re.compile(r"([A-Za-z_]\w*)")
#: 变参占位写法（形参表里的 `...`；按形态是三个点，由语言包声明驱动调用侧实参形态）
_VARIADIC_MARK = "..."


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
    params: list[str] | None = None
    if call_args is not None and rest.startswith(call_args.open):
        # function-like：`define NAME(a, b) body
        matched = call_args.match_args(rest, 0)
        if matched is None:
            raise ConfigError(
                f"宏 {def_name!r} 的形参表未闭合（`{call_args.open}` 无配对 "
                f"`{call_args.close}`）：{arg.strip()!r}"
            )
        params_text, body_idx = matched
        # 变参记号**保留在形参记录里**（`...`）：展开侧据此区分"真变参宏"与
        # "非变参宏里误用 `__VA_ARGS__`"（后者报错，不靠"超出具名实参即变参"猜）。
        params = [p for p in call_args.split(params_text) if p]
        ctx["macro_defs"][def_name] = rest[body_idx:].strip()
        ctx.setdefault("_func_params", {})[def_name] = params
    else:
        ctx["macro_defs"][def_name] = rest.strip()
    # 定义事件（原始源行号；`params=None` = 非函数宏）——两用：调用点事实的
    # **顺序语义**修正（`macro_timeline.py`，读 line/name/params），以及展开器
    # 的**定义时间线**（`expand_tokens(events=...)`，读 line/op/body/params）。
    body = ctx["macro_defs"][def_name]
    ctx.setdefault("_active_defs", {})[def_name] = body
    active_funcs = ctx.setdefault("_active_funcs", {})
    if params is not None:
        active_funcs[def_name] = list(params)
    else:
        active_funcs.pop(def_name, None)
    ctx.setdefault("_macro_events", []).append(
        {
            "line": int(ctx.get("_cur_raw_line") or ctx.get("_cur_line_no") or 0),
            "name": def_name,
            "params": list(params) if params is not None else None,
            "op": "define",
            "body": body,
        }
    )
