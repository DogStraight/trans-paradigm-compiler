"""ifdef — `ifdef / `ifndef / `else / `elsif / `endif 指令处理器

控制条件栈，构建条件块结构（ctx["_cond_blocks"]），并做保真占位：
块结束（endif）时把"非管线内容"（边界指令行 + inactive 分支原文）压缩成
唯一注释占位写入 clean_source，渲染后由 restore_condition_blocks 替换回原文。

栈帧格式：
    {"active", "found_active", "cond", "block", "cur_branch"}
条件块结构（ctx["_cond_blocks"] 内元素）：
    { "ifdef_line", "cond", "negated", "boundary_lines",
      "branches": [ {"cond", "is_else", "active", "lines"}, ... ],
      "cur_branch" }
Doc: preprocessor/README.md
"""

from .registry import register


def _is_macro_defined(ctx, cond):
    """判断条件宏是否已定义：外部 undefine（-U）优先，其次外部 predefined（-D），
    最后源码内 `define 的宏表。"""
    if cond in ctx.get("_undefine", set()):
        return False
    if cond in ctx.get("_predefined", {}):
        return True
    return cond in ctx.get("macro_defs", {})


def _new_branch(cond, is_else, active):
    return {"cond": cond, "is_else": is_else, "active": active, "lines": []}


def _make_placeholder(ctx, lines):
    """把一段原文压缩成唯一注释占位，记录映射后返回占位注释行。"""
    seq = ctx.get("_cond_seq", 0)
    ctx["_cond_seq"] = seq + 1
    ph_id = f"tpc:cond:{seq}"
    ctx.setdefault("_cond_placeholders", {})[ph_id] = "\n".join(lines)
    return f"// <{ph_id}>"


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


@register("ifdef", kind="control")
def handle_ifdef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `ifdef COND。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析条件
    cond = stripped[len(prefix) + len("ifdef ") :].strip()
    defined = _is_macro_defined(ctx, cond)
    stack: list = ctx.setdefault("_ifdef_stack", [])
    branch = _new_branch(cond, False, defined)
    parent_branch = stack[-1].get("cur_branch") if stack else None
    block = {
        "ifdef_line": stripped,
        "cond": cond,
        "negated": False,
        "depth": len(stack),
        "parent_branch": parent_branch,
        "boundary_lines": [stripped],
        "branches": [branch],
        "cur_branch": branch,
    }
    ctx.setdefault("_cond_blocks", []).append(block)
    stack.append({
        "active": defined,
        "found_active": defined,
        "cond": cond,
        "block": block,
        "cur_branch": branch,
    })


@register("ifndef", kind="control")
def handle_ifndef(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `ifndef COND。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析条件
    cond = stripped[len(prefix) + len("ifndef ") :].strip()
    defined = _is_macro_defined(ctx, cond)
    stack: list = ctx.setdefault("_ifdef_stack", [])
    branch = _new_branch(cond, False, not defined)
    parent_branch = stack[-1].get("cur_branch") if stack else None
    block = {
        "ifdef_line": stripped,
        "cond": cond,
        "negated": True,
        "depth": len(stack),
        "parent_branch": parent_branch,
        "boundary_lines": [stripped],
        "branches": [branch],
        "cur_branch": branch,
    }
    ctx.setdefault("_cond_blocks", []).append(block)
    stack.append({
        "active": not defined,
        "found_active": not defined,
        "cond": cond,
        "block": block,
        "cur_branch": branch,
    })


def _switch_branch(ctx: dict, stripped: str, cond, is_else: bool) -> None:
    """切换当前块到新分支（else/elsif 用），并记录边界行。"""
    stack: list = ctx.get("_ifdef_stack", [])
    if not stack:
        return
    frame = stack[-1]
    block = frame["block"]
    block["boundary_lines"].append(stripped)
    if not frame["found_active"]:
        if cond is None:
            active = True  # else：前面全未选中
        else:
            active = _is_macro_defined(ctx, cond)
        frame["found_active"] = active
    else:
        active = False
    branch = _new_branch(cond, is_else, active)
    block["branches"].append(branch)
    block["cur_branch"] = branch
    frame["cur_branch"] = branch
    frame["active"] = active
    if cond is not None:
        frame["cond"] = cond


@register("else", kind="control")
def handle_else(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `else。前面分支都未选中才激活。"""
    del prefix, _name  # DirectiveHandler 协议签名参数，本 handler 不消费
    _switch_branch(ctx, stripped, None, True)


@register("elsif", kind="control")
def handle_elsif(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `elsif COND。语义同 else + ifdef。"""
    del _name  # DirectiveHandler 协议签名参数，本 handler 从 stripped 解析条件
    cond = stripped[len(prefix) + len("elsif ") :].strip()
    _switch_branch(ctx, stripped, cond, False)


@register("endif", kind="control")
def handle_endif(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理 `endif：flush 当前块，弹出栈帧。"""
    del prefix, _name  # DirectiveHandler 协议签名参数，本 handler 不消费
    stack: list = ctx.get("_ifdef_stack", [])
    if not stack:
        return
    block = stack[-1]["block"]
    block["boundary_lines"].append(stripped)
    out = _flush_block(ctx, block)
    stack.pop()
    if stack:
        # 外层存在：flush 结果归入外层栈顶当前分支（作为外层块内容）
        outer = stack[-1].get("cur_branch")
        if outer is not None:
            outer["lines"].extend(out)
    else:
        ctx["_inject_lines"].extend(out)
