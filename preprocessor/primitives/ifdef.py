"""ifdef — 条件指令处理器族（`ifdef` / `ifndef` / `else` / `elsif` / `endif`）。

控制条件栈，构建条件块结构（ctx["_cond_blocks"]），并做保真占位：
块结束（endif）时把"非管线内容"（边界指令行 + inactive 分支原文）压缩成
唯一注释占位写入 clean_source，渲染后由 restore_condition_blocks 替换回原文。

**条件块机制是共用的**：`#if` / `#elif`（表达式求值，见 `primitives/condition.py`）与
`ifdef` / `elsif`（宏名语义）走同一套开块/切支/收块函数；分支活性由调用方算好传入。

栈帧格式：
    {"active", "found_active", "parent_active", "seen_else", "cond", "block", "cur_branch"}
条件块结构（ctx["_cond_blocks"] 内元素）：
    { "ifdef_line", "cond", "negated", "parent_active", "boundary_lines",
      "branches": [ {"cond", "is_else", "active", "lines"}, ... ],
      "cur_branch" }
行账本：branches[].lines / boundary_lines 存 (原始行号, 文本) 对——条件
压缩会改变行数，clean→raw 行映射必须逐行记账；边界行行号取自
ctx["_cur_line_no"]（scan_directives 主循环维护，测试直调 handler 时为 None）。

**配对诊断**（未闭合条件块 / 多余 `#else` 等）只在语言包声明 `[condition]` 时给出
（C 标准要求诊断；未声明的语言包 —— 如 verilog —— 行为零变化，见 `cond_diag`）。
Doc: preprocessor/README.md
"""

from lexer.comment_syntax import load_comment_syntax

from .._markers import line_marker
from ..condition import is_macro_defined, load_condition_syntax
from .registry import register, split_directive


def _new_branch(cond, is_else, active):
    return {"cond": cond, "is_else": is_else, "active": active, "lines": []}


def current_frame(ctx: dict):
    """栈顶条件帧（无块 → None）。"""
    stack: list = ctx.get("_ifdef_stack", [])
    return stack[-1] if stack else None


def outer_active(ctx: dict) -> bool:
    """当前行是否在活跃分支内：**外层全部帧**都活跃才活跃（整条栈链）。"""
    stack: list = ctx.get("_ifdef_stack", [])
    return all(f.get("active", True) for f in stack)


def condition_syntax(ctx: dict):
    """本语言包的条件求值声明（`[condition]`；未声明 → None；按 ctx 缓存）。"""
    if "_condition_syntax" not in ctx:
        rules_dir = ctx.get("rules_dir")
        ctx["_condition_syntax"] = (
            load_condition_syntax(rules_dir) if rules_dir else None
        )
    return ctx["_condition_syntax"]


def cond_diag(ctx: dict, message: str, *, kind: str = "condition-balance") -> None:
    """条件指令诊断（仅当语言包声明了 `[condition]`；否则静默保持既有行为）。"""
    if condition_syntax(ctx) is None:
        return
    ctx.setdefault("_cond_diags", []).append(
        {
            "kind": kind,
            "message": message,
            "line": ctx.get("_cur_line_no"),
            "column": ctx.get("_cur_line_indent", 0) + 1,
        }
    )


def _make_placeholder(ctx, lines):
    """把一段原文压缩成唯一注释占位，返回 (归属行号, 占位注释行)。

    lines 为 (原始行号, 文本) 账本对；占位行本身是注释（无 token），归属
    取段内首个已知行号，全未知（直接调用 handler 的测试路径）为 None。
    占位**注释形态**由语言包声明（引擎不认识 `//` / `/* */`）——ctx 必须
    带 rules_dir（scan_directives 设置；直调 handler 的测试须自备）。
    """
    rules_dir = ctx.get("rules_dir")
    if not rules_dir:
        raise ValueError(
            "[preprocessor] 条件块占位需要 ctx['rules_dir']——"
            "占位注释形态从语言包声明取（引擎不认识注释标点）"
        )
    seq = ctx.get("_cond_seq", 0)
    ctx["_cond_seq"] = seq + 1
    ph_id = f"tpc:cond:{seq}"
    ctx.setdefault("_cond_placeholders", {})[ph_id] = "\n".join(t for _, t in lines)
    anchor = next((n for n, _ in lines if n is not None), None)
    return anchor, line_marker(load_comment_syntax(rules_dir), ph_id)


def _flush_block(ctx, block):
    """把条件块写入输出：active 分支内容行 + 非管线段（边界/inactive）压缩成占位。

    返回 flush 出的行列表；由调用方决定写入 _inject_lines 或归入外层分支。
    """
    out_lines = []
    pending = []
    bl = block["boundary_lines"]
    break_lines = bl[1:-1]  # else/elsif 行
    pending.append(bl[0])  # ifdef/ifndef 行
    for i, branch in enumerate(block["branches"]):
        if branch["active"]:
            if pending:
                out_lines.append(_make_placeholder(ctx, pending))
                pending = []
            out_lines.extend(branch["lines"])
        else:
            pending.extend(branch["lines"])
        if i < len(break_lines):
            pending.append(break_lines[i])
    pending.append(bl[-1])  # endif 行
    if pending:
        out_lines.append(_make_placeholder(ctx, pending))
    return out_lines


def open_cond_block(
    ctx: dict, stripped: str, *, cond: str, active: bool, negated: bool
) -> None:
    """开一个条件块并压栈（分支活性由调用方算好传入）。

    `parent_active` = 开块那一刻的外层活性：表达式求值（`#if` / `#elif`）据此在
    inactive 外层里**跳过求值**（C99：被跳过组的控制表达式不求值、不报表达式错误）。
    """
    parent_active = outer_active(ctx)
    branch = _new_branch(cond, False, active)
    frame = {
        "active": active,
        "found_active": active,
        "parent_active": parent_active,
        "seen_else": False,
        "cond": cond,
        "block": None,
        "cur_branch": branch,
    }
    block = {
        "ifdef_line": stripped,
        "cond": cond,
        "negated": negated,
        "depth": len(ctx.get("_ifdef_stack", [])),
        "parent_branch": (current_frame(ctx) or {}).get("cur_branch"),
        "parent_active": parent_active,
        "boundary_lines": [(ctx.get("_cur_line_no"), stripped)],
        "branches": [branch],
        "cur_branch": branch,
    }
    frame["block"] = block
    ctx.setdefault("_cond_blocks", []).append(block)
    ctx.setdefault("_ifdef_stack", []).append(frame)


def switch_branch(
    ctx: dict, stripped: str, *, cond, is_else: bool, active: bool
) -> None:
    """切换当前块到新分支（else/elsif/elif 用），并记录边界行。

    活性规则由调用方给：默认分支（is_else）= 前面全未选中；条件分支 = 前面全未选中
    且本次条件成立（前支已选中 ⇒ 不再求值、恒 inactive）。
    """
    frame = current_frame(ctx)
    if frame is None:
        return
    block = frame["block"]
    block["boundary_lines"].append((ctx.get("_cur_line_no"), stripped))
    if is_else:
        frame["seen_else"] = True
    branch = _new_branch(cond, is_else, active)
    block["branches"].append(branch)
    block["cur_branch"] = branch
    frame["cur_branch"] = branch
    frame["active"] = active
    frame["found_active"] = frame["found_active"] or active
    if cond is not None:
        frame["cond"] = cond


def close_block(ctx: dict, stripped: str) -> None:
    """收尾当前条件块（endif）：flush 占位 + 弹栈 + 结果归入外层分支。"""
    stack: list = ctx.get("_ifdef_stack", [])
    if not stack:
        return
    block = stack[-1]["block"]
    block["boundary_lines"].append((ctx.get("_cur_line_no"), stripped))
    out = _flush_block(ctx, block)
    stack.pop()
    if stack:
        outer = stack[-1].get("cur_branch")
        if outer is not None:
            outer["lines"].extend(out)
    else:
        ctx["_inject_lines"].extend(out)


def _open_ifdef(stripped: str, prefix: str, ctx: dict, *, negated: bool) -> None:
    """`ifdef` / `ifndef`：宏名语义定活性后开块。"""
    keyword, arg = split_directive(stripped, prefix)
    cond = arg.strip()
    if not cond:
        cond_diag(ctx, f"条件指令缺宏名（`{prefix}{keyword}`）")
    defined = is_macro_defined(ctx, cond)
    active = not defined if negated else defined
    open_cond_block(ctx, stripped, cond=cond, active=active, negated=negated)


@register("ifdef", kind="control")
def handle_ifdef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `ifdef COND。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析条件
    _open_ifdef(stripped, prefix, ctx, negated=False)


@register("ifndef", kind="control")
def handle_ifndef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `ifndef COND。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析条件
    _open_ifdef(stripped, prefix, ctx, negated=True)


@register("else", kind="control")
def handle_else(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `else：前面分支都未选中才激活；配对错误给诊断（声明 [condition] 时）。"""
    del prefix  # DirectiveHandler 协议签名参数，本 handler 不消费
    frame = current_frame(ctx)
    if frame is None:
        cond_diag(ctx, f"多余的 `{_name}`（无匹配的条件块）")
        return
    if frame.get("seen_else"):
        cond_diag(ctx, f"`{_name}` 重复出现（同一条件块只能有一个默认分支）")
        return
    switch_branch(
        ctx, stripped, cond=None, is_else=True, active=not frame["found_active"]
    )


@register("elsif", kind="control")
def handle_elsif(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `elsif COND（**宏名语义**，verilog 族）：语义同 else + ifdef。"""
    frame = current_frame(ctx)
    if frame is None:
        cond_diag(ctx, f"多余的 `{_name}`（无匹配的条件块）")
        return
    if frame.get("seen_else"):
        cond_diag(ctx, f"`{_name}` 出现在默认分支之后（分支顺序非法）")
        return
    cond = split_directive(stripped, prefix)[1].strip()
    active = False if frame["found_active"] else is_macro_defined(ctx, cond)
    switch_branch(ctx, stripped, cond=cond, is_else=False, active=active)


@register("endif", kind="control")
def handle_endif(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `endif：flush 当前块，弹出栈帧。"""
    del prefix  # DirectiveHandler 协议签名参数，本 handler 不消费
    frame = current_frame(ctx)
    if frame is None:
        cond_diag(ctx, f"多余的 `{_name}`（无匹配的条件块）")
        return
    close_block(ctx, stripped)
