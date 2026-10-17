"""condition — `#if` / `#elif` 条件指令处理器（**整型常量表达式求值**，声明驱动）。

与 `ifdef` / `elsif`（宏名语义）共用同一套条件块机制（`ifdef.py` 的
`open_cond_block` / `switch_branch` / `close_block`）；本模块只负责"算分支活性"：

    #if  E     → 表达式求值（E 非零为真）
    #elif E    → 前面分支全未选中时才求值；已选中 ⇒ 不求值（C99 §6.10.1）

求值语义全部来自语言包 `[condition]` 声明（见 `preprocessor/condition.py`）；
语言包未声明 `[condition]` ⇒ 本处理器不接线（verilog 不声明 ⇒ 语义不变）。

**inactive 外层里不求值**（`open_cond_block` 记 `parent_active`）：C99 下被跳过组的
控制表达式不求值、其语法错误也不报（gcc 实测：`#if 0` 里的 `#if 1/0` 静默）。
Doc: preprocessor/README.md
"""

from ..condition import evaluate_condition
from .ifdef import (
    condition_syntax,
    cond_diag,
    current_frame,
    open_cond_block,
    outer_active,
    switch_branch,
)
from .registry import register, split_directive


def _expr_arg(stripped: str, prefix: str, ctx: dict) -> tuple[str, int]:
    """指令行 → (表达式文本, 表达式在源行内的 0-based 起始列)。"""
    _keyword, arg = split_directive(stripped, prefix)
    if not arg:
        return "", len(stripped)
    offset = stripped.find(arg, len(prefix))
    if offset < 0:  # pragma: no cover — split_directive 的 arg 必是 stripped 子串
        offset = len(prefix)
    return arg, ctx.get("_cur_line_indent", 0) + offset


def _eval_arg(
    stripped: str, prefix: str, ctx: dict, syn
) -> tuple[bool, list[dict]]:
    """表达式求值（诊断进 `ctx["_cond_diags"]`，不抛异常）。"""
    expr, column_base = _expr_arg(stripped, prefix, ctx)
    return evaluate_condition(
        expr,
        ctx,
        syn,
        line=int(ctx.get("_cur_line_no") or 0),
        column_base=column_base,
    )


@register("cond_if", kind="control")
def handle_cond_if(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `#if EXPR：求值定活性（inactive 外层不求值）。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析表达式
    syn = condition_syntax(ctx)
    if syn is None:
        return
    cond = split_directive(stripped, prefix)[1].strip()
    if outer_active(ctx):
        active, diags = _eval_arg(stripped, prefix, ctx, syn)
        ctx.setdefault("_cond_diags", []).extend(diags)
    else:
        active = False
    open_cond_block(ctx, stripped, cond=cond, active=active, negated=False)


@register("cond_elif", kind="control")
def handle_cond_elif(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `#elif EXPR：前支全未选中才求值（已选中 ⇒ 不求值、不报错）。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析表达式
    syn = condition_syntax(ctx)
    if syn is None:
        return
    frame = current_frame(ctx)
    if frame is None:
        cond_diag(ctx, "多余的 `elif`（无匹配的条件块）")
        return
    if frame.get("seen_else"):
        cond_diag(ctx, "`elif` 出现在默认分支之后（分支顺序非法）")
        return
    cond = split_directive(stripped, prefix)[1].strip()
    already = frame["found_active"]
    outer = frame.get("parent_active", True)
    if not already and outer:
        active, diags = _eval_arg(stripped, prefix, ctx, syn)
        ctx.setdefault("_cond_diags", []).extend(diags)
    else:
        active = False
    switch_branch(ctx, stripped, cond=cond, is_else=False, active=active)
