"""ifdef — `ifdef / `ifndef / `else / `elsif / `endif 指令处理器

这些 handler 不直接产生配置或数据，而是通过 ctx["_ifdef_stack"] 控制
scan_directives 的扫描流程，决定当前行是否进入输出。

栈帧格式：
    {"active": bool, "found_active": bool, "cond": str}
      active:       当前分支是否被选中
      found_active: 当前 ifdef 块中是否已有分支被选中（用于 else 判定）
"""

from .registry import register


@register("ifdef")
def handle_ifdef(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `ifdef COND。"""
    cond = stripped[len(prefix) + len("ifdef ") :].strip()
    macro_defs = ctx.get("macro_defs", {})
    defined = cond in macro_defs
    stack: list = ctx.setdefault("_ifdef_stack", [])
    stack.append({
        "active": defined,
        "found_active": defined,
        "cond": cond,
    })


@register("ifndef")
def handle_ifndef(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `ifndef COND。"""
    cond = stripped[len(prefix) + len("ifndef ") :].strip()
    macro_defs = ctx.get("macro_defs", {})
    defined = cond in macro_defs
    stack: list = ctx.setdefault("_ifdef_stack", [])
    stack.append({
        "active": not defined,
        "found_active": not defined,
        "cond": cond,
    })


@register("else")
def handle_else(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `else。

    如果前面的分支都没有被选中，则激活当前 else 分支；
    否则关闭。
    """
    stack: list = ctx.get("_ifdef_stack", [])
    if not stack:
        return
    frame = stack[-1]
    if not frame["found_active"]:
        frame["active"] = True
        frame["found_active"] = True
    else:
        frame["active"] = False


@register("elsif")
def handle_elsif(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `elsif COND。

    语义同 else + ifdef：前面的分支都未选中才检查条件。
    """
    cond = stripped[len(prefix) + len("elsif ") :].strip()
    stack: list = ctx.get("_ifdef_stack", [])
    if not stack:
        return
    frame = stack[-1]
    if not frame["found_active"]:
        macro_defs = ctx.get("macro_defs", {})
        defined = cond in macro_defs
        frame["active"] = defined
        frame["found_active"] = defined
        frame["cond"] = cond
    else:
        frame["active"] = False


@register("endif")
def handle_endif(stripped: str, prefix: str, name: str, ctx: dict) -> None:
    """处理 `endif。弹出栈帧。"""
    stack: list = ctx.get("_ifdef_stack", [])
    if stack:
        stack.pop()
