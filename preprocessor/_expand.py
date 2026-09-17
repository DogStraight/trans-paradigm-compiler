"""Macro expansion — strip directives, expand `` `NAME `` references.

Pipeline: scan_directives() → expand_tokens() → Lexer
Both operate on pure text, no token dependency.

指令处理由 primitives/registry.py 的注册表分发，新增指令不修改本文件。
Doc: preprocessor/README.md
"""

import re
from core.config_registry import declare_cfg
from core.token_protocol import anchor_name, anchor_salt
from lexer.comment_syntax import CommentSyntax, load_comment_syntax
from .primitives.registry import get_primitive, get_primitive_kind, list_primitives
from .primitives.include import resolve_source_dir
from ._bridge import make_marker
from ._markers import inline_marker, line_marker

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# preprocessor.macro_config
#   #sym:config = (root)  ← 无 section，取整个文件
#   格式: dict
#     { macro_recognition: { directive: { strategy, prefix }, call: { strategy, prefix } },
#       directives: { keyword: token_type, ... } }
_macro_cfg: dict = declare_cfg("preprocessor.macro_config", {}, __name__, "_macro_cfg")

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
        best: tuple[int, str, str] | None = None
        for start, end in pairs:
            k = line.find(start, i)
            if k >= 0 and (best is None or k < best[0]):
                best = (k, start, end)
        # 行注释起始标记在块注释起始之前 → 本行剩余部分是行注释文本
        for marker in line_markers:
            k = line.find(marker, i)
            if k >= 0 and (best is None or k < best[0]):
                return None
        if best is None:
            return None
        i = best[0] + len(best[1])
        state = best[2]
    return state


def _load_config() -> tuple[str, set[str]]:
    """Load macro config from ConfigRegistry → (prefix, directives_set)."""
    cfg = dict(_macro_cfg)
    recognition = cfg.get("macro_recognition", {})
    prefix = recognition.get("prefix", "`")
    configured = set(cfg.get("directives", {}).values())
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


# 宏调用后紧跟的位宽字面量后缀：`W'd0、`W'h1F、`W'sb101、`W'0 等
_LITERAL_SUFFIX_RE = re.compile(r"^'[sS]?[bBoOdDhH]?[0-9a-fA-FxXzZ_?]*")


def _build_macro_re(prefix: str) -> re.Pattern:
    return re.compile(rf"\{prefix}(\w+)")


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
    prefix, directives_set = _load_config()
    _MACRO_RE = _build_macro_re(prefix)

    if _include_stack is None:
        _include_stack = set()

    # include 配置（从 ConfigRegistry 读）
    inc_config = _get_include_config()

    # 搜索路径：CLI 传入的 search_dirs 优先，合并配置中的 search_dirs
    cli_dirs = search_dirs or []
    cfg_dirs = inc_config.get("search_dirs", [])
    src_dir = resolve_source_dir(source_path, rules_dir)
    all_dirs = cli_dirs + cfg_dirs + [src_dir, rules_dir]

    # Handler 共享上下文
    ctx = {
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
        "_include_stack": _include_stack,
        "source_dir": src_dir,
        "inc_dirs": all_dirs,
        "rules_dir": rules_dir,
        "_include_config": inc_config,
    }

    # ── 预合并延续行（反斜杠折行）──
    # 账本：每条输出行携带其**原始行号**（行与行号成对入列表）——clean 行数
    # 与原始行数不同（条件压缩/续行合并），行映射只能逐行记账，不能事后对齐。
    source, join_map = _join_continuation_lines(source)
    lines = source.split("\n")
    # 注释跨度扫描（定界符/行注释标记来自语言包声明）：注释内部的行**不是指令行**
    _syntax = load_comment_syntax(rules_dir)
    _block_pairs, _line_markers = _syntax.block_pairs, _syntax.line_starts
    _block_state: str | None = None

    for jno, line in enumerate(lines, 1):
        ctx["_cur_line_no"] = jno  # 控制指令 handler 记账用（边界行归属）
        stripped = line.strip()
        stack: list = ctx.get("_ifdef_stack", [])
        _inside_block = _block_state is not None
        _block_state = _advance_block_comment(line, _block_state, _block_pairs, _line_markers)

        if _inside_block or not stripped.startswith(prefix):
            # 非指令行（含块注释内部行）：归入栈顶块当前分支（flush 时决定管线/占位）；
            # 无块时直接进管线。注释内的 `ifdef/`endif 不是指令——按指令处理
            # 会丢行、甚至把注释截断成未闭合注释（实测）。
            if stack:
                branch = stack[-1].get("cur_branch")
                if branch is not None:
                    branch["lines"].append((jno, line))
            elif _is_ifdef_active(ctx):
                ctx["_inject_lines"].append((jno, line))
            continue

        # 从行首提取 directive 关键字（`define foo → "define"）
        after_prefix = stripped[len(prefix) :]
        space_pos = after_prefix.find(" ")
        directive_name = after_prefix[:space_pos] if space_pos > 0 else after_prefix

        # 行首宏调用（名字不在 directives 指令表，如 `debug(x);、`FORMAL_KEEP）
        if directive_name not in directives_set:
            if stack:
                branch = stack[-1].get("cur_branch")
                if branch is not None:
                    branch["lines"].append((jno, line))
            elif _is_ifdef_active(ctx):
                ctx["_inject_lines"].append((jno, line))
            continue

        handler_cfg = _directives_cfg.get(directive_name, {})
        if not handler_cfg.get("enabled", True):
            # 配置禁用：不执行 handler，但原文原位占位保留
            if _is_ifdef_active(ctx):
                _inject_directive_marker(ctx, stack, jno, line, _syntax)
            elif stack:
                branch = stack[-1].get("cur_branch")
                if branch is not None:
                    branch["lines"].append((jno, line))
            continue

        # 指令关键字 → op（预定义操作）绑定，kind 以 op 对应处理器为准
        op = handler_cfg.get("op", directive_name)
        kind = get_primitive_kind(op)
        if kind == "control":
            # 控制指令行（ifdef/else/endif）：负责条件栈，始终执行。
            # 不记录 directive_lines（由占位恢复），不归入分支内容（是块边界）。
            handler = get_primitive(op)
            if handler:
                handler(stripped, prefix, directive_name, ctx)
            continue

        # 副作用指令行（define/undef/include）
        if _is_ifdef_active(ctx):
            # 活跃分支内：执行 handler，原文原位占位（渲染后回插到原位置）
            handler = get_primitive(op)
            if handler:
                handler(stripped, prefix, directive_name, ctx)
            _inject_directive_marker(ctx, stack, jno, line, _syntax)
        elif stack:
            # inactive 分支内：不执行、不进 directive_lines，原文归入分支（占位保留）
            branch = stack[-1].get("cur_branch")
            if branch is not None:
                branch["lines"].append((jno, line))

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

    if not macro_defs:
        return (
            {},
            func_macros,
            condition_blocks,
            placeholders,
            directive_lines,
            clean_source,
            clean_to_raw,
        )

    # ---- Fully expand macro bodies (for reverser) ----
    # 带参宏 body 含形参占位，形参未绑定时不能预展开，跳过。
    expand_cfg = _get_expand_config()
    max_iter = expand_cfg.get("max_iterations", 128)
    # 体长上限：防递归宏指数膨胀（fuzz 2026-08-22 发现 MemoryError——
    # `` `define debug ( `debug ... ) `` 每次迭代体长翻倍，128 轮即
    # 2^128 长度）。超限宏停止展开（引用保留为未展开 token），软失败不崩溃。
    max_body_len = expand_cfg.get("max_body_len", 1 << 16)
    stalled: set[str] = set()
    for _ in range(max_iter):
        changed = False
        for name, body in list(macro_defs.items()):
            if name in func_macros or name in stalled:
                continue
            # 直接自引用（`X 出现在 X 自己的体里）：GCC 语义——递归宏引用
            # 不展开。预判跳过，避免进入翻倍循环。
            if name in _MACRO_RE.findall(body):
                stalled.add(name)
                continue
            new_body = _MACRO_RE.sub(
                lambda m: macro_defs.get(m.group(1), m.group(0)), body
            )
            if new_body != body:
                if len(new_body) > max_body_len:
                    stalled.add(name)  # 传递递归兜底：体积超限即停止
                    continue
                changed = True
                macro_defs[name] = new_body
        if not changed:
            break

    return (
        macro_defs,
        func_macros,
        condition_blocks,
        placeholders,
        directive_lines,
        clean_source,
        clean_to_raw,
    )


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
    d = block.get("depth", 0)
    # 当前块的子块范围：其后连续 depth 更大的块
    sub_end = idx + 1
    while sub_end < len(blocks) and blocks[sub_end].get("depth", 0) > d:
        sub_end += 1
    branches = block["branches"]
    for i, branch in enumerate(branches):
        new_def = set(define)
        new_undef = set(undefine)
        # 选中分支 i 需前面所有分支条件为假
        for j in range(i):
            c = branches[j].get("cond")
            if c:
                new_undef.add(c)
        if not branch.get("is_else"):
            c = branch.get("cond")
            if c:
                if i == 0 and block.get("negated"):
                    new_undef.add(c)  # ifndef 分支：条件未定义
                else:
                    new_def.add(c)  # ifdef / elsif 分支：条件已定义
        if idx + 1 < sub_end and blocks[idx + 1].get("parent_branch") is branch:
            # 有属于该分支的子块：先枚举子块（含其后所有块）
            _enumerate_rec(blocks, idx + 1, new_def, new_undef, out, max_configs)
        else:
            # 该分支下无子块：直接继续后续块
            _enumerate_rec(blocks, sub_end, new_def, new_undef, out, max_configs)


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


def _match_paren_args(line: str, open_idx: int) -> tuple[str, int]:
    """从 open_idx（`(` 位置）匹配括号，返回 (内部文本, 闭括号后位置)。

    未闭合时返回 (空串, len(line))，由调用方按容错处理。
    """
    depth = 0
    i = open_idx
    while i < len(line):
        c = line[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return line[open_idx + 1 : i], i + 1
        i += 1
    return "", len(line)


def _split_args(text: str) -> list[str]:
    """按顶层逗号分割实参（忽略括号/方括号内的逗号）。"""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for c in text:
        if c in "([":
            depth += 1
            cur.append(c)
        elif c in ")]":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur).strip())
    return parts


def _expand_func_call(
    name: str, args_text: str, func_macros: dict, macro_defs: dict
) -> str:
    """展开带参宏调用：body[形参 → 实参]。实参不足补空串，按形参顺序绑定。"""
    params = func_macros.get(name, [])
    arg_list = _split_args(args_text)
    body = macro_defs.get(name, "")
    for idx, p in enumerate(params):
        arg = arg_list[idx] if idx < len(arg_list) else ""
        body = re.sub(rf"\b{re.escape(p)}\b", lambda _: arg, body)
    return body


def _extend_literal_suffix(line: str, end: int) -> int:
    """扩展宏调用区间到其后的位宽字面量后缀（`W'd0 → `W'd0 整体纳入）。

    宏调用后紧跟 `'` 时（如 `W'd0、`W'h1F），token 替换若只换宏名会留下
    `tpc_marker_N'd0`（标识符 + 位宽字面量，非合法数字字面量，解析丢行）；
    把 `'<base><digits>` 一并纳入调用区间，token 替换整体，还原时整体回插原文。
    """
    m = _LITERAL_SUFFIX_RE.match(line[end:])
    if m and m.end() > 0:
        return end + m.end()
    return end


def _extend_macro_chain(line: str, end: int, macro_re: re.Pattern) -> int:
    """吞噬宏调用链：宏调用 + 位宽字面量后缀 + 后续相邻宏调用（`W'd`RST）。

    复合/嵌套宏调用（如 `W'd`RST = `W + 'd + `RST）token 替换成单个 token，
    source_text 为整段原文——避免拆成相邻 token 后粘连（tpc_marker_A tpc_marker_B
    无词边界，全词匹配还原失败）。
    """
    cur = end
    while True:
        nxt = _extend_literal_suffix(line, cur)
        if nxt > cur:
            cur = nxt
        m = macro_re.match(line[cur:])
        if m and m.start() == 0:  # 紧跟宏调用（无空白分隔）
            cur = cur + m.end()
            continue
        break
    return cur


def expand_tokens(
    source: str,
    macro_defs: dict[str, str],
    *,
    rules_dir: str,
    prefix: str = "`",
    func_macros: dict[str, list[str]] | None = None,
    semantic: bool = False,
) -> tuple[str, list[dict], list[dict], list[int]]:
    """在源码文本中展开宏调用（纯文本层），并注册统一锚 / 宏区间表。

    用正则搜索 `NAME，向左扫同步词，记录位置后替换宏体。
    带参宏（func_macros 中登记的名字）识别 `NAME( ... ) 调用并做形参替换。
    不再依赖 Token 流或 Lexer。

    rules_dir：语言包目录——锚以注释形态穿过管线，标点从声明取
    （`lexer/comment_syntax.py`，引擎不认识 `//` / `/* */`）。

    semantic=True（check 语义分析用，2026-08-29）：语句体宏（token 锚
    形态）改为**宏体展开**——锚只服务渲染还原，check 不需要还原、需要宏体
    语义（否则宏体内语句不可分析 + 锚被当未解析引用报 W002）。渲染路径
    （format/expand 命令）保持默认 semantic=False（锚 + 还原原文，保真不变）。

    锚形态（统一位置桥，见 _bridge）：
      line   整行占位：独占整行的宏调用（`debug(...)`）、行首空体宏
             （`FORMAL_KEEP reg ...）→ 整行替换为行注释占位，
             source_text = 整行原文（含宏调用），渲染后整行回插。
      sync   行内非空体宏（如 `assign z = `MIN(x, y);`）→ 保留 body 替换，
             记录同步词字段，由同步词窗口启发式回插（兼容现状）。

    Returns: (expanded_source, restoration_stack, macro_regions, line_map)
        line_map — **展开后行号（1-based）→ 源（clean）行号**：诊断回源用。
            逐行就地替换 → 输出行数只可能因宏体含换行而增加，一行源行对应
            一串连续输出行，故 list[int] 足够（无需完整区间表）。
        restoration_stack — 统一锚列表（渲染路径还原用），每项含 marker/source_text/mode。
        macro_regions — **宏区间表**（仅 semantic=True 有意义）：每条"宏体被铺进
            文本"的调用一项，含它在**源文本**里的区间（`src_line`/`src_col`/
            `src_end_col`）与它在**展开结果**里的字符区间（`offset`/`end_offset`），
            以及 `name`/`source_text`（宏调用原文）/`body`（实际铺进的内容；宏体末行
            含行注释时末尾补了一个换行，见下）。
            它是外层处理宏的单一事实源（ADR-0017 决策 3）：定位"哪些内容来自
            哪条宏"→ 渲染侧 raw 拼接、诊断宏归因都靠它。
            semantic=False 时为空表（那条路径用锚还原）。
    """
    _MACRO_RE = re.compile(rf"\{prefix}(\w+)")
    func_macros = func_macros or {}
    _syntax = load_comment_syntax(rules_dir)
    restoration_stack: list[dict] = []
    lines = source.split("\n")
    # 锚名盐：随源文本走（同一文件内所有锚共用一个盐，序号区分彼此）。
    salt = anchor_salt(source)

    _macro_seq = 0
    # 宏区间表：按行收集 → 行处理完算行内列 → 全部行完算绝对字符偏移
    regions_by_line: dict[int, list[dict]] = {}

    def _next_macro_seq() -> int:
        nonlocal _macro_seq
        _macro_seq += 1
        return _macro_seq

    for line_no, line in enumerate(lines, 1):
        macro_matches: list[tuple[int, int, str, str, bool, str]] = []
        # 本行被“铺宏体”的调用（原起列, 原止列, 名字, 是否带参, 宏体）
        line_regions: list[tuple[int, int, str, bool, str]] = []
        consumed_until = -1
        for m in _MACRO_RE.finditer(line):
            if m.start() < consumed_until:
                continue  # 已被前一个宏调用链吞噬（`W'd`RST 嵌套）
            name = m.group(1)
            if name in func_macros and line[m.end() :].startswith("("):
                args_text, close_idx = _match_paren_args(line, m.end())
                if close_idx > m.end():
                    body = _expand_func_call(
                        name, args_text, func_macros, macro_defs
                    )
                    end = _extend_macro_chain(line, close_idx, _MACRO_RE)
                    consumed_until = max(consumed_until, end)
                    macro_matches.append(
                        (m.start(), end, body, name, True, args_text)
                    )
                    continue
            body = macro_defs.get(name)
            if body is None:
                continue
            end = _extend_macro_chain(line, m.end(), _MACRO_RE)
            consumed_until = max(consumed_until, end)
            macro_matches.append((m.start(), end, body, name, False, ""))

        if not macro_matches:
            continue

        # ── 行首空体宏（`FORMAL_KEEP reg ...`）→ 整行占位 ──
        # 行首空体宏是 decl 修饰符（如 `FORMAL_KEEP reg [3:0] q;`），唯一 token
        # 替换会破坏 decl 解析（标识符 + decl 相邻）；整行占位回插整行原文。
        single_head_empty = (
            len(macro_matches) == 1
            and not macro_matches[0][2]
            and line[: macro_matches[0][0]].strip() == ""
        )
        if single_head_empty:
            marker = make_marker("macro", _next_macro_seq())
            lines[line_no - 1] = line_marker(_syntax, marker)
            restoration_stack.append(
                {
                    "marker": marker,
                    "source_text": line,
                    "mode": "line",
                    "kind": "macro",
                }
            )
            continue

        # ── 其他宏 → 锚替换 ──
        # 非空 body 宏（assert/MIN 等）→ 唯一 token（tpc_marker_N），随 AST 确定
        # 渲染，还原时 find 精确；不依赖注释通道（restore_comments 启发式对多锚
        # 不可靠）或同步词容差。
        # 空 body 宏（`TV80DELAY 1'b1` 行内占位）→ 行内块注释锚（inline）：
        #   空宏 token 替换会留下 `tpc_marker_N 1'b1` 相邻原子（id + 位宽字面量）
        #   不可解析；行内注释 marker 是 trivia，parser 跳过，还原时原位回插
        #   原文宏调用（块注释位置 = 宏调用位置）。
        parts = list(line)
        forward_entries: list[dict] = []
        for col, end, body, name, is_func, args_text in reversed(macro_matches):
            source_text = line[col:end]  # 宏调用原文（含反引号与实参）
            if not body:
                # 空 body 宏：行内注释锚（marker 唯一，还原精确）
                marker = make_marker("macro", _next_macro_seq())
                parts[col:end] = inline_marker(_syntax, marker)
                forward_entries.append(
                    {
                        "marker": marker,
                        "source_text": source_text,
                        "mode": "inline",
                        "kind": "macro",
                    }
                )
                continue
            if body.lstrip().startswith("="):
                # 赋值后缀宏（body 以 `=` 开头，如 ice40 `ICE40_DEFAULT_ASSIGNMENT_1`
                # body=`= 1'b1`，端口默认值位 `input NAME `M`）：token 替换会把
                # `= 1'b1` 顶成 `tpc_marker_N` 标识符——`input NAME tpc_marker_N`
                # 两个相邻 id，linter/parser 双拒（ice40 默认配置 34 错，M1）。
                # 改用 inline+body 区间还原：
                # marker 注释 + body 原文保留在源码（parser 跳过注释看到
                # `input NAME = 1'b1`，Declarator @Init? 兜住端口默认值），
                # 还原时按 [marker..body] 区间替换回宏调用原文（source_text）。
                marker = make_marker("macro", _next_macro_seq())
                parts[col:end] = inline_marker(_syntax, marker) + body
                forward_entries.append(
                    {
                        "marker": marker,
                        "source_text": source_text,
                        "mode": "inline",
                        "kind": "macro",
                        "body": body,
                    }
                )
                continue
            token = anchor_name(_next_macro_seq(), salt)
            if semantic:
                # check 语义展开：宏体替换（body 原文含分号），不建还原锚，
                # 只记宏区间（源区间 + 展开后区间，供外层定位/raw 拼接）
                #
                # 宏体**末行含行注释**（如 `define LUI 7'b01 // lui rd,imm）时
                # 补一个换行：否则宏调用**同行的后续内容**（`... ==`LUI;` 的 `;`）
                # 落进注释里被吞掉 → 语句丢分号 → 发现器级联失守（darkriscv
                # 实测 81 条）。补换行让被注释吞掉的部分回到下一行，解析照常
                # （Verilog 不看行）；输出侧不受影响（渲染走宏调用原文）。
                tail = body.rsplit("\n", 1)[-1]
                spliced = body + "\n" if "//" in tail else body
                parts[col:end] = spliced
                line_regions.append((col, end, name, is_func, spliced))
                continue
            # 锚形态 = 普通标识符（`__tpc_marker_<salt>_<n>`，保留命名空间）：
            # 语言包不认识宏，锚与标识符同形 → 表达式/标识符槽位照常解析。
            # 宏的**位置**由外层（扩展/raw 拼接）处理，不给语言包留语法槽位
            # （宏位置本质上是文本任意的，逐槽位声明补不齐且可能错渲染，
            # 见 ADR-0017 决策 3）。
            # 独占一行的宏调用（行首 ∧ 行尾）补分号：锚名 + `;` 按裸任务
            # 调用语句可解析（1364-2005 A.6.9 task_enable），裸标识符不是合法
            # 语句——lint/parser 都会拒（ice40 cells_sim 的 `SB_DFF_INIT 等
            # 语句体宏独占一行无分号，真实语料实证）。只对"行首 ∧ 行尾"补：
            # 行尾但非行首（如 `parameter P_D = `D` 后换行 `)`）是构造续行，
            # 补分号会炸（ref_macro_complex 回归）；表达式位宏（调用后还有
            # 内容）不补，保持既有行为。已知边界：宏调用独占一行夹在跨行
            # 表达式中间（`a +` / `` `M`` / `+ b;`）会被误补，语料/真实代码
            # 均无此形态（属坏风格），可接受。
            # 注意：anchor 的 marker 保持无分号原文（还原按锚名整串匹配 +
            # (?!\w) 边界），`;` 只进替换文本。
            replacement = token
            if (
                "".join(parts[:col]).strip() == ""
                and "".join(parts[end:]).strip() == ""
            ):
                replacement += ";"
            parts[col:end] = replacement
            forward_entries.append(
                {
                    "marker": token,
                    "source_text": source_text,
                    "mode": "token",
                    "kind": "macro",
                    # 源文本位置（展开前行/起列/止列）：宏调用在 raw 源上的区间，
                    # 供宏边界节点（MacroCall）双向映射用。
                    "line": line_no,
                    "col": col,
                    "end_col": end,
                }
            )
        restoration_stack.extend(reversed(forward_entries))
        lines[line_no - 1] = "".join(parts)

        if line_regions:
            # 展开后行内列 = 原列 + 左侧各宏替换的长度增量（按原列升序累加）
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
            regions_by_line[line_no] = pending

    # 行内列 → 展开结果的绝对字符区间（消费方按 offset 定位 token/节点）
    macro_regions: list[dict] = []
    base = 0
    for idx, line_text in enumerate(lines, 1):
        for entry in regions_by_line.get(idx, ()):
            entry["offset"] = base + entry.pop("in_line_col")
            entry["end_offset"] = entry["offset"] + entry.pop("in_line_len")
            macro_regions.append(entry)
        base += len(line_text) + 1

    # 行映射（诊断回源）：**展开后行号（1-based）→ 源（clean）行号**。
    # 依据：本函数逐行就地替换，输出行数只可能因宏体含换行而增加
    # （`lines[i] = "".join(parts)` 内嵌 \n）→ 一行源行对应一串连续输出行。
    out_to_src: list[int] = []
    for _src_no, _text in enumerate(lines, 1):
        out_to_src.extend([_src_no] * (_text.count("\n") + 1))

    return "\n".join(lines), restoration_stack, macro_regions, out_to_src
