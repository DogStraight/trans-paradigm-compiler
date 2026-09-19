"""Macro expansion — strip directives, expand `` `NAME `` references.

Pipeline: scan_directives() → expand_tokens() → Lexer
Both operate on pure text, no token dependency.

指令处理由 primitives/registry.py 的注册表分发，新增指令不修改本文件。
Doc: preprocessor/README.md
"""

import os
import re
from dataclasses import dataclass, field
from core.config_registry import declare_cfg
from core.errors import ConfigError
from core.token_protocol import IDENT_RE
from lexer.comment_syntax import CommentSyntax, load_comment_syntax
from .primitives.registry import (
    get_primitive,
    get_primitive_kind,
    list_primitives,
    split_directive,
)
from .primitives.include import resolve_source_dir
from ._bridge import make_marker
from ._markers import inline_marker, line_marker
from .macro_policy import (
    MODE_INLINE,
    MODE_LINE,
    MODE_SPLICE,
    load_macro_policy,
    plan_macro,
)
from .macro_shape import (
    MacroCallArgs,
    load_macro_call_args,
    load_macro_call_suffix,
    load_macro_shapes,
    macro_keywords,
)

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# preprocessor.macro_config 由 preprocessor/macro_shape.py 读取（形态声明；
# 本文件按 rules_dir 解析后交给它，不再自带一份声明）。

# preprocessor.expand
#   #sym:config = [expand]
#   格式: dict — { max_iterations: int }
_expand_cfg: dict = declare_cfg("preprocessor.expand", {"max_iterations": 128}, __name__, "_expand_cfg")

# preprocessor.directives
#   #sym:config = [directive_handlers]
#   格式: dict
#     { define: { enabled: bool },
#       include: { enabled: bool, search_dirs: list[str], silent: bool } }
_directives_cfg: dict = declare_cfg("preprocessor.directives", {}, __name__, "_directives_cfg")

# preprocessor.continuation
#   #sym:config = [continuation]
#   格式: dict — { enabled: bool, character: str }
_continuation_cfg: dict = declare_cfg("preprocessor.continuation", {}, __name__, "_continuation_cfg")


def _join_continuation_lines(
    source: str, cfg: dict | None = None
) -> tuple[str, list[int]]:
    """合并反斜杠延续行，并产出行映射。

    行尾为 continuation 字符时，与下一行合并为同一逻辑行。
    合并后的行若仍以 continuation 结尾，继续合并（支持链式折行）。
    cfg 支持:
        enabled: bool (default True)
        character: str (default "\\")

    Returns: (joined_source, join_map)
        join_map — **合并后行号（1-based）→ 原始行号（1-based）**：续段是
        首行的物理延伸，映射取合并段首行（诊断位置以段首行为准）。
    """
    if cfg is None:
        cfg = dict(_continuation_cfg)
    if not cfg.get("enabled", True):
        return source, list(range(1, source.count("\n") + 2))
    char = cfg.get("character", "\\")
    lines = source.split("\n")
    result: list[str] = []
    join_map: list[int] = []
    i = 0
    while i < len(lines):
        jno = i + 1
        line = lines[i]
        stripped = line.rstrip()
        if stripped.endswith(char) and i + 1 < len(lines):
            prefix = stripped[: -len(char)]
            merged = prefix
            i += 1
            while i < len(lines):
                next_stripped = lines[i].rstrip()
                if next_stripped.endswith(char):
                    merged += next_stripped[: -len(char)]
                    i += 1
                else:
                    merged += lines[i].lstrip()
                    i += 1
                    break
            result.append(merged)
        else:
            result.append(line)
            i += 1
        join_map.append(jno)
    return "\n".join(result), join_map


def _get_expand_config() -> dict[str, int]:
    return _expand_cfg


def _get_include_config() -> dict:
    return dict(_directives_cfg.get("include", {}))


def _advance_block_comment(
    line: str,
    state: str | None,
    pairs: tuple[tuple[str, str], ...],
    line_markers: tuple[str, ...],
) -> str | None:
    """按行推进块注释状态；返回下一行行首时的状态（结束标记或 None）。

    同行内的开/闭按出现顺序配对（开闭同行 → 状态不变）；行注释起始标记之后
    的行内文本属于行注释（不跨行），不再扫描定界符。
    已知近似：字符串内的定界符形态（如 `$display("/*")`）会被当成注释开启——
    与捕获器不同源（捕获器兼顾字符串）；此处保守但极罕见，后续如需精确可
    改用捕获器算跨度。
    """
    i = 0
    while i < len(line):
        if state is not None:
            k = line.find(state, i)
            if k < 0:
                return state
            i = k + len(state)
            state = None
            continue
        best = _next_open_delimiter(line, i, pairs)
        marker_at = _next_line_marker(line, i, line_markers)
        # 行注释起始标记在块注释起始之前 → 本行剩余部分是行注释文本
        if marker_at >= 0 and (best is None or marker_at < best[0]):
            return None
        if best is None:
            return None
        i = best[0] + len(best[1])
        state = best[2]
    return state


def _next_open_delimiter(
    line: str, i: int, pairs: tuple[tuple[str, str], ...]
) -> tuple[int, str, str] | None:
    """i 之后最早的块注释起始 → `(位置, 起始标记, 结束标记)`；无 → None。"""
    best: tuple[int, str, str] | None = None
    for start, end in pairs:
        k = line.find(start, i)
        if k >= 0 and (best is None or k < best[0]):
            best = (k, start, end)
    return best


def _next_line_marker(line: str, i: int, markers: tuple[str, ...]) -> int:
    """i 之后最早的行注释起始标记位置；无 → -1。"""
    best = -1
    for marker in markers:
        k = line.find(marker, i)
        if k >= 0 and (best < 0 or k < best):
            best = k
    return best


def _load_config(rules_dir: str) -> tuple[str, set[str]]:
    """宏形态声明 → (前缀文本, 指令名集合)。

    两者都从语言包 `[macro_recognition]` 的**形态生产式**推导（前缀 token 名 →
    符号文本；指令候选名 → 去 `macro.` 前缀的关键字）——前缀不在引擎里硬编码
    （解析见 preprocessor/macro_shape.py）。

    按 rules_dir 解析该语言包的声明（与 `Lexer(rules_dir=...)` 同源），不复用
    全局已加载配置：同进程切语言时不串味（c4 无宏形态 → 空前缀 + 空指令集）。
    """
    shapes = load_macro_shapes(rules_dir=rules_dir)
    directive = shapes.get("directive")
    prefix = directive.prefix if directive is not None else ""
    configured = set(macro_keywords(directive)) if directive is not None else set()
    # 已注册的指令处理器名也算指令：未加载配置时也能区分"指令行 vs 行首宏调用"
    directives = configured | set(list_primitives())
    return prefix, directives


def _is_ifdef_active(ctx: dict) -> bool:
    """检查当前行是否在活跃的 ifdef 分支内。

    必须检查整条栈链：如果任意外层帧 inactive，当前行也不应输出。
    """
    stack: list = ctx.get("_ifdef_stack", [])
    if not stack:
        return True
    return all(f.get("active", True) for f in stack)


def _build_macro_re(prefix: str) -> re.Pattern:
    """宏调用正则（前缀 + 名字）；未声明前缀 → 永不匹配（该语言无宏形态）。

    名字用引擎级标识符形态（`core/token_protocol.IDENT_RE`）——与 lexer 的
    宏形态识别同源，不在文本层另写一份名字正则。
    """
    if not prefix:
        return re.compile(r"(?!)")
    return re.compile(re.escape(prefix) + f"({IDENT_RE.pattern})")


# ── 纯文本展开（新方案）──


def _inject_directive_marker(
    ctx: dict, stack: list, jno: int, line: str, syntax: CommentSyntax
) -> None:
    """active 指令行（define/undef/include）原位占位。

    指令行从 token 流剥离（不进入 clean_source），但在原位置插入
    整行占位注释（注释形态由语言包声明，见 `_markers.line_marker`），
    原文记入 placeholders；渲染后由 restore_anchors 原位回插，实现指令行
    位置保真（不再堆到文件头）。
    原文存**完整行（含前导缩进）**——还原要恢复原文形态，剥缩进会让
    嵌套 ifdef 内的 define 还原后顶格（ref 里 define 有 2/4 空格缩进）。
    占位行按 (原始行号, 文本) 入账本——1:1 替换不改变行数，行映射照常。
    """
    seq = ctx["_directive_seq"]
    ctx["_directive_seq"] = seq + 1
    marker = f"tpc:directive:{seq}"
    placeholder = line_marker(syntax, marker)
    ctx.setdefault("_directive_placeholders", {})[marker] = line
    if stack:
        branch = stack[-1].get("cur_branch")
        if branch is not None:
            branch["lines"].append((jno, placeholder))
    else:
        ctx["_inject_lines"].append((jno, placeholder))


def scan_directives(
    source: str,
    rules_dir: str,
    *,
    source_path: str | None = None,
    _include_stack: set[str] | None = None,
    search_dirs: list[str] | None = None,
    predefined: dict[str, str] | None = None,
    undefine: set[str] | None = None,
) -> tuple[
    dict[str, str],
    dict[str, list[str]],
    list[dict],
    dict[str, str],
    list[str],
    str,
    list[int | None],
]:
    """扫描源文件中的宏指令，构建宏表并返回清洗后的源码。

    Returns: (macro_defs, func_macros, condition_blocks, placeholders,
              directive_lines, clean_source, clean_to_raw)
        macro_defs:      name → body（object-like 全展开；function-like 保留形参占位）
        func_macros:     name → [形参列表]（function-like 宏）
        condition_blocks: 条件块结构列表（每块含 branches/cond/active/lines）
        placeholders:    {占位 id → 原文段}，渲染后由 restore_condition_blocks 替换回
        directive_lines:  副作用指令行原文（define/include/undef）
        clean_source:     去掉指令行、inactive 分支压缩成占位后的源码
        clean_to_raw:     clean 行（1-based）→ 原始源行（1-based）；续行合并
                          取段首行、增删行按实际归属记账；include 拼接行不属
                          本源文件 → None（不可映射，消费方保守回退）。诊断
                          回源时与 `expand_tokens` 的展开级映射复合使用。
    """
    prefix, directives_set = _load_config(rules_dir)
    macro_re = _build_macro_re(prefix)
    ctx = _build_scan_ctx(
        rules_dir, source_path, search_dirs, predefined, undefine, _include_stack
    )

    # ── 预合并延续行（反斜杠折行）──
    # 账本：每条输出行携带其**原始行号**（行与行号成对入列表）——clean 行数
    # 与原始行数不同（条件压缩/续行合并），行映射只能逐行记账，不能事后对齐。
    source, join_map = _join_continuation_lines(source)
    _scan_lines(source.split("\n"), ctx, prefix, directives_set, rules_dir)

    result = _collect_scan_result(ctx, join_map)
    if result[0]:  # 有宏定义才预展开（供 reverser）
        _expand_macro_bodies(result[0], result[1], macro_re)
    return result


def _build_scan_ctx(
    rules_dir: str,
    source_path: str | None,
    search_dirs: list[str] | None,
    predefined: dict[str, str] | None,
    undefine: set[str] | None,
    include_stack: set[str] | None,
) -> dict:
    """扫描会话上下文：宏表 + 条件栈/占位序号 + 路径与配置（handler 共享）。

    搜索路径：CLI 传入的 search_dirs 优先，合并配置中的 search_dirs。
    带参宏的实参形态（语言包 `[macro_recognition]` 的 call_args / arg_separator）：
    定义侧形参表与展开侧实参表共用它（引擎不硬编码 `(` / `,`）。
    """
    inc_config = _get_include_config()
    src_dir = resolve_source_dir(source_path, rules_dir)
    all_dirs = (
        (search_dirs or [])
        + inc_config.get("search_dirs", [])
        + [src_dir, rules_dir]
    )
    return {
        "macro_defs": {},
        "_func_params": {},
        "_cond_blocks": [],
        "_cond_seq": 0,
        "_cond_placeholders": {},
        "_directive_seq": 0,
        "_directive_placeholders": {},
        "_predefined": dict(predefined) if predefined else {},
        "_undefine": set(undefine) if undefine else set(),
        "directive_lines": [],
        "_inject_lines": [],
        "_include_stack": include_stack if include_stack is not None else set(),
        "source_dir": src_dir,
        "inc_dirs": all_dirs,
        "rules_dir": rules_dir,
        "_include_config": inc_config,
        "_call_args": load_macro_call_args(rules_dir=rules_dir),
    }


def _collect_scan_result(ctx: dict, join_map: list) -> tuple:
    """把 ctx 里的累积状态整理成返回契约（含 clean 行 → 原始行映射）。"""
    macro_defs = ctx["macro_defs"]
    func_macros = ctx["_func_params"]
    condition_blocks = ctx.get("_cond_blocks", [])
    placeholders = dict(ctx.get("_cond_placeholders", {}))
    placeholders.update(ctx.get("_directive_placeholders", {}))
    directive_lines = ctx["directive_lines"]
    inject_lines = ctx["_inject_lines"]
    clean_source = "\n".join(text for _, text in inject_lines)
    # clean 行（1-based）→ 原始行（1-based）：合并段取首行；include 拼接行
    # 不属于本源文件 → None（不可映射，消费方保守回退展开行号）
    clean_to_raw = [
        join_map[jno - 1] if jno and 1 <= jno <= len(join_map) else None
        for jno, _ in inject_lines
    ]
    return (
        macro_defs,
        func_macros,
        condition_blocks,
        placeholders,
        directive_lines,
        clean_source,
        clean_to_raw,
    )


def _scan_lines(
    lines: list[str], ctx: dict, prefix: str, directives_set: set[str], rules_dir: str
) -> None:
    """逐行扫描：指令行分派到处理器，非指令行按条件栈归属。

    注释跨度扫描（定界符/行注释标记来自语言包声明）：**块注释内部的行不是指令
    行**——按指令处理会丢行、甚至把注释截断成未闭合注释（实测）。
    """
    _syntax = load_comment_syntax(rules_dir)
    _block_pairs, _line_markers = _syntax.block_pairs, _syntax.line_starts
    block_state: str | None = None

    for jno, line in enumerate(lines, 1):
        ctx["_cur_line_no"] = jno  # 控制指令 handler 记账用（边界行归属）
        stack: list = ctx.get("_ifdef_stack", [])
        inside_block = block_state is not None
        block_state = _advance_block_comment(
            line, block_state, _block_pairs, _line_markers
        )
        if inside_block or not line.strip().startswith(prefix):
            _route_line(ctx, stack, jno, line)
            continue
        _handle_directive(ctx, stack, jno, line, prefix, directives_set, _syntax)


def _route_line(ctx: dict, stack: list, jno: int, line: str) -> None:
    """非指令行（含块注释内部行、行首宏调用）：按条件栈归属。

    有块 → 归栈顶块当前分支（flush 时决定管线/占位）；无块且当前条件活跃 →
    直接进管线（`_inject_lines`）。
    """
    if stack:
        _append_to_branch(stack, jno, line)
    elif _is_ifdef_active(ctx):
        ctx["_inject_lines"].append((jno, line))


def _append_to_branch(stack: list, jno: int, line: str) -> None:
    """把行归入栈顶块的当前分支（无当前分支时丢弃——块边界行）。"""
    branch = stack[-1].get("cur_branch")
    if branch is not None:
        branch["lines"].append((jno, line))


def _handle_directive(
    ctx: dict,
    stack: list,
    jno: int,
    line: str,
    prefix: str,
    directives_set: set[str],
    syntax,
) -> None:
    """指令行分派：控制指令（条件栈）/ 副作用指令（define/undef/include）。

    行首宏调用（名字不在指令表，如 `debug(x);）不是指令 → 按普通行归属。
    配置禁用的指令不执行 handler，但原文原位占位保留。
    """
    stripped = line.strip()
    # 从行首提取 directive 关键字（`define foo → "define"）：切分 = 前缀 +
    # 关键字 + 空白（`primitives/registry.split_directive`，与 handler 取参同源；
    # 关键字拼写来自语言包候选，引擎不写死、也不假定分隔符是单个空格）
    directive_name = split_directive(stripped, prefix)[0]
    if directive_name not in directives_set:
        _route_line(ctx, stack, jno, line)
        return

    handler_cfg = _directives_cfg.get(directive_name, {})
    op = handler_cfg.get("op", directive_name)
    if not handler_cfg.get("enabled", True):
        if _is_ifdef_active(ctx):
            _inject_directive_marker(ctx, stack, jno, line, syntax)
        elif stack:
            _append_to_branch(stack, jno, line)
        return

    # 指令关键字 → op（预定义操作）绑定，kind 以 op 对应处理器为准
    if get_primitive_kind(op) == "control":
        # 控制指令行（ifdef/else/endif）：负责条件栈，始终执行。
        # 不记录 directive_lines（由占位恢复），不归入分支内容（是块边界）。
        _invoke_directive(op, stripped, prefix, directive_name, ctx)
        return

    # 副作用指令行（define/undef/include）
    if _is_ifdef_active(ctx):
        # 活跃分支内：执行 handler，原文原位占位（渲染后回插到原位置）
        _invoke_directive(op, stripped, prefix, directive_name, ctx)
        _inject_directive_marker(ctx, stack, jno, line, syntax)
    elif stack:
        # inactive 分支内：不执行、不进 directive_lines，原文归入分支（占位保留）
        _append_to_branch(stack, jno, line)


def _invoke_directive(
    op: str, stripped: str, prefix: str, name: str, ctx: dict
) -> None:
    """执行指令处理器（op 绑定到 primitive；未注册 → 不执行）。"""
    handler = get_primitive(op)
    if handler:
        handler(stripped, prefix, name, ctx)


def _expand_macro_bodies(macro_defs: dict, func_macros: dict, macro_re) -> None:
    """原地全展开宏体（供 reverser），迭代到不动点。

    体长上限：防递归宏指数膨胀（fuzz 2026-08-22 发现 MemoryError——
    `` `define debug ( `debug ... ) `` 每次迭代体长翻倍，128 轮即 2^128 长度）。
    超限宏停止展开（引用保留为未展开 token），软失败不崩溃。
    """
    expand_cfg = _get_expand_config()
    max_iter = expand_cfg.get("max_iterations", 128)
    max_body_len = expand_cfg.get("max_body_len", 1 << 16)
    stalled: set[str] = set()
    for _ in range(max_iter):
        if not _expand_round(macro_defs, func_macros, stalled, macro_re, max_body_len):
            break


def _expand_round(
    macro_defs: dict,
    func_macros: dict,
    stalled: set[str],
    macro_re,
    max_body_len: int,
) -> bool:
    """全体宏体各展一轮 → 是否有变化（供迭代到不动点）。

    带参宏 body 含形参占位，形参未绑定时不能预展开，跳过。直接自引用（`X 出现
    在 X 自己的体里）按 GCC 语义不展开——预判跳过，避免进入翻倍循环。
    """
    changed = False
    for name, body in list(macro_defs.items()):
        if name in func_macros or name in stalled:
            continue
        if name in macro_re.findall(body):
            stalled.add(name)
            continue
        new_body = macro_re.sub(
            lambda m: macro_defs.get(m.group(1), m.group(0)), body
        )
        if new_body == body:
            continue
        if len(new_body) > max_body_len:
            stalled.add(name)  # 传递递归兜底：体积超限即停止
            continue
        macro_defs[name] = new_body
        changed = True
    return changed


# ── 多路径诊断：条件块叶路径枚举 ──


def _enumerate_rec(
    blocks: list[dict],
    idx: int,
    define: set[str],
    undefine: set[str],
    out: list[dict],
    max_configs: int,
) -> None:
    """递归枚举条件块叶路径。blocks 为先序（外层先），depth 表示嵌套层级。"""
    if len(out) >= max_configs:
        return
    if idx >= len(blocks):
        out.append({"define": set(define), "undefine": set(undefine)})
        return
    block = blocks[idx]
    branches = block["branches"]
    sub_end = _subtree_end(blocks, idx, block.get("depth", 0))
    for i, branch in enumerate(branches):
        new_def, new_undef = _branch_env(branches, i, define, undefine, block)
        # 有属于该分支的子块 → 先枚举子块；否则直接继续后续块
        child_idx = idx + 1
        if child_idx < sub_end and blocks[child_idx].get("parent_branch") is branch:
            _enumerate_rec(blocks, child_idx, new_def, new_undef, out, max_configs)
        else:
            _enumerate_rec(blocks, sub_end, new_def, new_undef, out, max_configs)


def _subtree_end(blocks: list[dict], idx: int, depth: int) -> int:
    """当前块的子块范围末尾下标（其后连续 depth 更大的块）。"""
    sub_end = idx + 1
    while sub_end < len(blocks) and blocks[sub_end].get("depth", 0) > depth:
        sub_end += 1
    return sub_end


def _branch_env(
    branches: list[dict], i: int, define: set[str], undefine: set[str], block: dict
) -> tuple[set[str], set[str]]:
    """选中分支 i 时的 `(define, undefine)` 假设集。

    选中 i 需前面所有分支条件为假（前面分支的 cond 进 undefine）；本分支 cond
    按方向计入：ifndef（首分支且块 negated）→ undefine，其它 → define；
    `is_else` / 无 cond 不加任何假设。
    """
    new_def = set(define)
    new_undef = set(undefine)
    for j in range(i):
        c = branches[j].get("cond")
        if c:
            new_undef.add(c)
    if branches[i].get("is_else"):
        return new_def, new_undef
    c = branches[i].get("cond")
    if not c:
        return new_def, new_undef
    if i == 0 and block.get("negated"):
        new_undef.add(c)  # ifndef 分支：条件未定义
    else:
        new_def.add(c)  # ifdef / elsif 分支：条件已定义
    return new_def, new_undef


def enumerate_conditions(
    blocks: list[dict], max_configs: int | None = None
) -> list[dict]:
    """枚举条件块的所有叶分支路径假设（多路径诊断用）。

    blocks 来自 scan_directives 的 condition_blocks（先序，含 depth）。
    返回 list[dict]，每项 {"define": set[str], "undefine": set[str]}，
    可直接作为 scan_directives(predefined=..., undefine=...) 的注入参数。
    枚举数受 max_configs 上限约束（防 2^N 分支爆炸），默认读 preprocessor.expand。
    """
    if max_configs is None:
        max_configs = _get_expand_config().get("max_configs", 64)
    configs: list[dict] = []
    _enumerate_rec(blocks, 0, set(), set(), configs, max_configs)
    return configs


def _expand_func_call(
    name: str,
    args_text: str,
    func_macros: dict,
    macro_defs: dict,
    call_args: MacroCallArgs,
) -> str:
    """展开带参宏调用：body[形参 → 实参]。实参不足补空串，按形参顺序绑定。"""
    params = func_macros.get(name, [])
    arg_list = call_args.split(args_text)
    body = macro_defs.get(name, "")
    for idx, p in enumerate(params):
        arg = arg_list[idx] if idx < len(arg_list) else ""
        body = re.sub(rf"\b{re.escape(p)}\b", lambda _: arg, body)
    return body


def _extend_literal_suffix(
    line: str, end: int, suffix_re: re.Pattern | None
) -> int:
    """扩展宏调用区间到其后的字面量后缀（`` `W'd0 `` → 整个调用区间）。

    后缀形态由语言包声明（`[macro_recognition].suffix_after_call`）；未声明 →
    不扩展。纳入后缀是为了让替换结果与 **token 边界对齐**：`` `W'd0 `` 整个换成
    一个 token（宏体），还原按 token 区间回插宏调用原文（ADR-0017 决策 3/4）。
    """
    if suffix_re is None:
        return end
    m = suffix_re.match(line[end:])
    if m and m.end() > 0:
        return end + m.end()
    return end


def _extend_macro_chain(
    line: str, end: int, macro_re: re.Pattern, suffix_re: re.Pattern | None
) -> int:
    """吞噬宏调用链：宏调用 + 后随字面量后缀 + 后续相邻宏调用（`` `W'd`RST ``）。

    相邻宏调用合并成单个调用区间：否则拆成相邻 token 后无词边界，还原按 token
    区间回插会错位（宏名可能成为更长锚名前缀）。
    """
    cur = end
    while True:
        nxt = _extend_literal_suffix(line, cur, suffix_re)
        if nxt > cur:
            cur = nxt
        m = macro_re.match(line[cur:])
        if m and m.start() == 0:  # 紧跟宏调用（无空白分隔）
            cur = cur + m.end()
            continue
        break
    return cur


def _call_site(
    line: str,
    line_no: int,
    col: int,
    end: int,
    body: str,
    name: str,
    is_func: bool,
    args_text: str,
    only_call_in_line: bool,
) -> dict:
    """宏调用点的**通用文本事实**（引擎给处置策略的输入，无语言知识）。"""
    before, after = line[:col], line[end:]
    return {
        "name": name,
        "body": body,
        "is_func": is_func,
        "args_text": args_text,
        "line": line_no,
        "col": col,
        "end": end,
        "line_text": line,
        "before": before,
        "after": after,
        "at_line_start": before.strip() == "",
        "at_line_end": after.strip() == "",
        "only_call_in_line": only_call_in_line,
    }


def _splice_body(body: str, syntax: CommentSyntax) -> str:
    """语义展开铺进流的宏体文本（`splice` 方案的文本面）。

    宏体末行含**行注释**（起始标记由语言包声明，引擎不认识 `//`）时补一个换行：
    否则宏调用**同行的后续内容**（如 `... ==`LUI;` 的 `;`）会落进注释里被吞 →
    语句丢分号 → 发现器级联失守（darkriscv 实测 81 条）。补换行让被吞的部分回到
    下一行，解析照常（语言语义上换行不是语句边界）；输出侧不受影响（渲染走宏调用
    原文）。
    """
    tail = body.rsplit("\n", 1)[-1]
    if any(mark in tail for mark in syntax.line_starts):
        return body + "\n"
    return body


@dataclass
class _MacroExpandCtx:
    """展开会话状态（原为 `expand_tokens` 的闭包变量，显式化以便助手提到模块级）。

    属性分两类：
    - **构造后不变**：`macro_re` / `macro_defs` / `func_macros` / `call_args` /
      `suffix_re` / `policy` / `syntax`（语言包声明与宏表）。
    - **逐行累积**：`lines`（就地替换）/ `restoration_stack`（还原锚）/
      `regions_by_line`（宏区间，行处理完算行内列）/ `seq`（锚序号，走 `next_seq()`）。
    """

    macro_re: re.Pattern
    macro_defs: dict[str, str]
    func_macros: dict[str, list[str]]
    call_args: Any
    suffix_re: Any
    policy: Any
    syntax: CommentSyntax
    lines: list[str]
    restoration_stack: list[dict] = field(default_factory=list)
    regions_by_line: dict[int, list[dict]] = field(default_factory=dict)
    seq: int = 0

    def next_seq(self) -> int:
        """锚序号（自增；`make_marker` 的唯一性来源）。"""
        self.seq += 1
        return self.seq


def expand_tokens(
    source: str,
    macro_defs: dict[str, str],
    *,
    rules_dir: str,
    prefix: str = "`",
    func_macros: dict[str, list[str]] | None = None,
) -> tuple[str, list[dict], list[dict], list[int]]:
    """在源码文本中展开宏调用（纯文本层），并注册统一锚 / 宏区间表。

    用正则搜索 `NAME，向左扫同步词，记录位置后替换宏体。
    带参宏（func_macros 中登记的名字）识别 `NAME( ... ) 调用并做形参替换。
    不再依赖 Token 流或 Lexer。

    rules_dir：语言包目录——锚以注释形态穿过管线，标点从声明取
    （`lexer/comment_syntax.py`，引擎不认识 `//` / `/* */`）。

    处置由**语言包策略**决定（`[capabilities] macro_policy`；未声明 → 默认 `splice`）。
    引擎执行的处置（机制面，见 macro_policy.py；与铺条目 mode 同词）：
      splice   宏体铺进流（+ 宏区间；末行含行注释时补换行，见 _splice_body）
      line     整行占位（行注释锚），source_text = 整行原文
      inline   行内注释锚（原位回插宏调用原文）

    Returns: (expanded_source, restoration_stack, macro_regions, line_map)
        line_map — **展开后行号（1-based）→ 源（clean）行号**：诊断回源用。
            逐行就地替换 → 输出行数只可能因宏体含换行而增加，一行源行对应
            一串连续输出行，故 list[int] 足够（无需完整区间表）。
        restoration_stack — 统一锚列表（`line`/`inline` 置位用），每项含
            marker/source_text/mode。
        macro_regions — **宏区间表**：每条"宏体被铺进文本"的调用一项，含它在
            **源文本**里的区间（`src_line`/`src_col`/`src_end_col`）与它在**展开
            结果**里的字符区间（`offset`/`end_offset`），以及 `name`/`source_text`
            （宏调用原文）/`body`（实际铺进的内容；宏体末行含行注释时末尾补了
            一个换行，见下）。
            它是外层处理宏的单一事实源（ADR-0017 决策 3）：定位"哪些内容来自
            哪条宏"→ 渲染侧 raw 拼接、诊断宏归因都靠它。
    """
    _MACRO_RE = _build_macro_re(prefix)
    func_macros = func_macros or {}
    # 实参形态与后随字面量后缀都由语言包声明（引擎不硬编码 `(` / `,` / `'d`）
    call_args = load_macro_call_args(rules_dir=rules_dir)
    suffix_re = load_macro_call_suffix(rules_dir=rules_dir)
    if func_macros and call_args is None:
        raise ConfigError(
            "[macro_recognition] 有待参宏（func_macros 非空）却未声明实参形态："
            "call_args（如 \"bracket.l_parentheses,args,bracket.r_parentheses\"）"
            "+ arg_separator（如 \"symbol.base.comma\"）——声明形式见 "
            "preprocessor/README.md"
        )
    ctx = _MacroExpandCtx(
        macro_re=_MACRO_RE,
        macro_defs=macro_defs,
        func_macros=func_macros,
        call_args=call_args,
        suffix_re=suffix_re,
        # 宏处置策略（语言包 `[capabilities] macro_policy`；未声明 → 引擎默认
        # splice，见 macro_policy.py）：引擎只执行处置，不判定"该怎么处置"。
        policy=load_macro_policy(rules_dir),
        syntax=load_comment_syntax(rules_dir),
        lines=source.split("\n"),
    )
    lines = ctx.lines

    for line_no, line in enumerate(lines, 1):
        macro_matches = _collect_macro_matches(ctx, line)
        if not macro_matches:
            continue

        # ── 处置方案（引擎给事实、语言包策略给枚举；见 macro_policy.py）──
        plans = [
            plan_macro(
                ctx.policy,
                _call_site(
                    line,
                    line_no,
                    col,
                    end,
                    body,
                    name,
                    is_func,
                    args_text,
                    len(macro_matches) == 1,
                ),
            )
            for col, end, body, name, is_func, args_text in macro_matches
        ]

        if _try_line_mode(ctx, line_no, line, plans, len(macro_matches)):
            continue

        # ── 逐调用执行处置（文本操作在引擎：锚书写 / 文本替换 / 区间记账）──
        new_line, forward_entries, line_regions = _run_plans(
            ctx, line, macro_matches, plans
        )
        ctx.restoration_stack.extend(reversed(forward_entries))
        lines[line_no - 1] = new_line

        if line_regions:
            ctx.regions_by_line[line_no] = _line_region_entries(
                line, line_no, line_regions
            )

    # 行内列 → 展开结果的绝对字符区间（消费方按 offset 定位 token/节点）
    macro_regions = _absolute_regions(lines, ctx.regions_by_line)

    # 行映射（诊断回源）：**展开后行号（1-based）→ 源（clean）行号**。
    # 依据：本函数逐行就地替换，输出行数只可能因宏体含换行而增加
    # （`lines[i] = ...` 内嵌 \n）→ 一行源行对应一串连续输出行。
    out_to_src = _out_to_src_map(lines)

    return(
        "\n".join(lines), ctx.restoration_stack, macro_regions, out_to_src
    )


def _match_one(
    ctx: "_MacroExpandCtx", line: str, m
) -> tuple[int, str, str, bool, str] | None:
    """单个正则命中 → `(end, body, name, is_func, args_text)`；不可展开 → None。

    带参调用：名字在 func_macros 且后随调用开始符，且实参可配对 → 形参替换；
    否则（含带参形态但实参未闭合）回退当同名的无参宏。
    """
    name = m.group(1)
    if (
        ctx.call_args is not None
        and name in ctx.func_macros
        and line[m.end() :].startswith(ctx.call_args.open)
    ):
        matched = ctx.call_args.match_args(line, m.end())
        if matched is not None:
            args_text, close_idx = matched
            body = _expand_func_call(
                name, args_text, ctx.func_macros, ctx.macro_defs, ctx.call_args
            )
            end = _extend_macro_chain(line, close_idx, ctx.macro_re, ctx.suffix_re)
            return end, body, name, True, args_text
    body = ctx.macro_defs.get(name)
    if body is None:
        return None
    end = _extend_macro_chain(line, m.end(), ctx.macro_re, ctx.suffix_re)
    return end, body, name, False, ""


def _collect_macro_matches(ctx: "_MacroExpandCtx", line: str) -> list[tuple]:
    """本行的宏调用（原起列, 原止列, 宏体, 名字, 是否带参, 实参文本）。"""
    matches: list[tuple] = []
    consumed_until = -1
    for m in ctx.macro_re.finditer(line):
        if m.start() < consumed_until:
            continue  # 已被前一个宏调用链吞噬（`W'd`RST 嵌套）
        hit = _match_one(ctx, line, m)
        if hit is None:
            continue
        end, body, name, is_func, args_text = hit
        consumed_until = max(consumed_until, end)
        matches.append((m.start(), end, body, name, is_func, args_text))
    return matches


def _try_line_mode(
    ctx: "_MacroExpandCtx", line_no: int, line: str, plans: list[dict], count: int
) -> bool:
    """整行占位（`line`）：整行换成行注释锚，source_text = 整行原文。

    该方案只在"本行仅此一个宏调用"时成立——否则会吞掉同行的其他调用。
    """
    if not any(p["mode"] == MODE_LINE for p in plans):
        return False
    if count != 1:
        raise ConfigError(
            "[macro_policy] line 方案要求该行只有这一个宏调用"
            f"（第 {line_no} 行有 {count} 个）"
        )
    marker = make_marker("macro", ctx.next_seq())
    ctx.lines[line_no - 1] = line_marker(ctx.syntax, marker)
    ctx.restoration_stack.append(
        {
            "marker": marker,
            "source_text": line,
            "mode": MODE_LINE,
            "kind": "macro",
        }
    )
    return True


def _run_plans(
    ctx: "_MacroExpandCtx",
    line: str,
    macro_matches: list[tuple],
    plans: list[dict],
) -> tuple[str, list[dict], list[tuple]]:
    """逐调用执行处置（**倒序**，避免列偏移互相影响）：→ (新行, 还原锚, 区间)。

    文本操作在引擎：锚书写 / 文本替换 / 区间记账。
    - `inline`：行内注释锚（marker 唯一，还原精确）；块注释是 trivia，parser
      跳过，还原时原位回插原文宏调用。
    - `splice`：宏体文本铺进流，不建还原锚，只记宏区间（源区间 + 展开后区间）。
    """
    parts = list(line)
    forward_entries: list[dict] = []
    line_regions: list[tuple] = []
    for (col, end, body, name, is_func, _args), plan in reversed(
        list(zip(macro_matches, plans))
    ):
        source_text = line[col:end]  # 宏调用原文（含反引号与实参）
        if plan["mode"] == MODE_INLINE:
            marker = make_marker("macro", ctx.next_seq())
            parts[col:end] = inline_marker(ctx.syntax, marker)
            forward_entries.append(
                {
                    "marker": marker,
                    "source_text": source_text,
                    "mode": MODE_INLINE,
                    "kind": "macro",
                }
            )
            continue
        spliced = _splice_body(body, ctx.syntax)
        parts[col:end] = spliced
        line_regions.append((col, end, name, is_func, spliced))
    return "".join(parts), forward_entries, line_regions


def _line_region_entries(
    line: str, line_no: int, line_regions: list[tuple]
) -> list[dict]:
    """行内区间 → 待定条目（展开后列 = 原列 + 左侧各宏替换的长度增量）。"""
    delta = 0
    pending: list[dict] = []
    for s_col, s_end, name, is_func, body in sorted(line_regions):
        pending.append(
            {
                "name": name,
                "source_text": line[s_col:s_end],
                "is_func": is_func,
                "body": body,
                "src_line": line_no,
                "src_col": s_col,
                "src_end_col": s_end,
                "in_line_col": s_col + delta,
                "in_line_len": len(body),
            }
        )
        delta += len(body) - (s_end - s_col)
    return pending


def _absolute_regions(lines: list[str], regions_by_line: dict[int, list[dict]]) -> list[dict]:
    """行内区间（列）→ 展开结果的绝对字符区间（行号 1-based）。"""
    macro_regions: list[dict] = []
    base = 0
    for idx, line_text in enumerate(lines, 1):
        for entry in regions_by_line.get(idx, ()):
            entry["offset"] = base + entry.pop("in_line_col")
            entry["end_offset"] = entry["offset"] + entry.pop("in_line_len")
            macro_regions.append(entry)
        base += len(line_text) + 1
    return macro_regions


def _out_to_src_map(lines: list[str]) -> list[int]:
    """展开后行号（1-based）→ 源行号：逐行按它含的 \n 数展开成下标表。"""
    out_to_src: list[int] = []
    for src_no, text in enumerate(lines, 1):
        out_to_src.extend([src_no] * (text.count("\n") + 1))
    return out_to_src
