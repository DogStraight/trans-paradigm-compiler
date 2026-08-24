"""Macro expansion — strip directives, expand `` `NAME `` references.

Pipeline: scan_directives() → expand_tokens() → Lexer
Both operate on pure text, no token dependency.

指令处理由 primitives/registry.py 的注册表分发，新增指令不修改本文件。
"""

import re
from core.config_registry import declare_cfg
from .primitives.registry import get_primitive, get_primitive_kind, list_primitives
from .primitives.include import resolve_source_dir
from ._bridge import make_marker

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


def _join_continuation_lines(source: str, cfg: dict | None = None) -> str:
    """合并反斜杠延续行。

    行尾为 continuation 字符时，与下一行合并为同一逻辑行。
    合并后的行若仍以 continuation 结尾，继续合并（支持链式折行）。
    cfg 支持:
        enabled: bool (default True)
        character: str (default "\\")
    """
    if cfg is None:
        cfg = dict(_continuation_cfg)
    if not cfg.get("enabled", True):
        return source
    char = cfg.get("character", "\\")
    lines = source.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
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
    return "\n".join(result)


def _get_expand_config() -> dict[str, int]:
    return _expand_cfg


def _get_include_config() -> dict:
    return dict(_directives_cfg.get("include", {}))


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


def _inject_directive_marker(ctx: dict, stack: list, line: str) -> None:
    """active 指令行（define/undef/include）原位占位。

    指令行从 token 流剥离（不进入 clean_source），但在原位置插入
    `// <tpc:directive:N>` 整行注释 marker，原文记入 placeholders；渲染后由
    restore_anchors 原位回插，实现指令行位置保真（不再堆到文件头）。
    原文存**完整行（含前导缩进）**——还原要恢复原文形态，剥缩进会让
    嵌套 ifdef 内的 define 还原后顶格（ref 里 define 有 2/4 空格缩进）。
    """
    seq = ctx["_directive_seq"]
    ctx["_directive_seq"] = seq + 1
    marker = f"tpc:directive:{seq}"
    ctx.setdefault("_directive_placeholders", {})[marker] = line
    if stack:
        branch = stack[-1].get("cur_branch")
        if branch is not None:
            branch["lines"].append(f"// <{marker}>")
    else:
        ctx["_inject_lines"].append(f"// <{marker}>")


def scan_directives(
    source: str,
    rules_dir: str,
    *,
    source_path: str | None = None,
    _include_stack: set[str] | None = None,
    search_dirs: list[str] | None = None,
    predefined: dict[str, str] | None = None,
    undefine: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, list[str]], list[dict], dict[str, str], list[str], str]:
    """扫描源文件中的宏指令，构建宏表并返回清洗后的源码。

    Returns: (macro_defs, func_macros, condition_blocks, placeholders, directive_lines, clean_source)
        macro_defs:      name → body（object-like 全展开；function-like 保留形参占位）
        func_macros:     name → [形参列表]（function-like 宏）
        condition_blocks: 条件块结构列表（每块含 branches/cond/active/lines）
        placeholders:    {占位 id → 原文段}，渲染后由 restore_condition_blocks 替换回
        directive_lines:  副作用指令行原文（define/include/undef）
        clean_source:     去掉指令行、inactive 分支压缩成占位后的源码
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
    source = _join_continuation_lines(source)
    lines = source.split("\n")

    for line in lines:
        stripped = line.strip()
        stack: list = ctx.get("_ifdef_stack", [])

        if not stripped.startswith(prefix):
            # 非指令行：归入栈顶块当前分支（flush 时决定管线/占位）；无块时直接进管线
            if stack:
                branch = stack[-1].get("cur_branch")
                if branch is not None:
                    branch["lines"].append(line)
            elif _is_ifdef_active(ctx):
                ctx["_inject_lines"].append(line)
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
                    branch["lines"].append(line)
            elif _is_ifdef_active(ctx):
                ctx["_inject_lines"].append(line)
            continue

        handler_cfg = _directives_cfg.get(directive_name, {})
        if not handler_cfg.get("enabled", True):
            # 配置禁用：不执行 handler，但原文原位占位保留
            if _is_ifdef_active(ctx):
                _inject_directive_marker(ctx, stack, line)
            elif stack:
                branch = stack[-1].get("cur_branch")
                if branch is not None:
                    branch["lines"].append(line)
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
            _inject_directive_marker(ctx, stack, line)
        elif stack:
            # inactive 分支内：不执行、不进 directive_lines，原文归入分支（占位保留）
            branch = stack[-1].get("cur_branch")
            if branch is not None:
                branch["lines"].append(line)

    macro_defs = ctx["macro_defs"]
    func_macros = ctx["_func_params"]
    condition_blocks = ctx.get("_cond_blocks", [])
    placeholders = dict(ctx.get("_cond_placeholders", {}))
    placeholders.update(ctx.get("_directive_placeholders", {}))
    directive_lines = ctx["directive_lines"]
    clean_source = "\n".join(ctx["_inject_lines"])

    if not macro_defs:
        return {}, func_macros, condition_blocks, placeholders, directive_lines, clean_source

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

    return macro_defs, func_macros, condition_blocks, placeholders, directive_lines, clean_source


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
    fragment 为整段原文——避免拆成相邻 token 后粘连（tpc_marker_A tpc_marker_B
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
    prefix: str = "`",
    func_macros: dict[str, list[str]] | None = None,
) -> tuple[str, list[dict]]:
    """在源码文本中展开宏调用（纯文本层），并注册统一锚。

    用正则搜索 `NAME，向左扫同步词，记录位置后替换宏体。
    带参宏（func_macros 中登记的名字）识别 `NAME( ... ) 调用并做形参替换。
    不再依赖 Token 流或 Lexer。

    锚形态（统一位置桥，见 _bridge）：
      line   整行占位：独占整行的宏调用（`debug(...)`）、行首空体宏
             （`FORMAL_KEEP reg ...）→ 整行替换为 `// <tpc:macro:N>` 占位，
             fragment = 整行原文（含宏调用），渲染后整行回插。
      sync   行内非空体宏（如 `assign z = `MIN(x, y);`）→ 保留 body 替换，
             记录同步词字段，由同步词窗口启发式回插（兼容现状）。

    Returns: (expanded_source, restoration_stack)
        restoration_stack — 统一锚列表，每项含 marker/fragment/mode 等。
    """
    _MACRO_RE = re.compile(rf"\{prefix}(\w+)")
    func_macros = func_macros or {}
    restoration_stack: list[dict] = []
    lines = source.split("\n")

    _macro_seq = 0

    def _next_macro_seq() -> int:
        nonlocal _macro_seq
        _macro_seq += 1
        return _macro_seq

    for line_no, line in enumerate(lines, 1):
        macro_matches: list[tuple[int, int, str, str, bool, str]] = []
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
            lines[line_no - 1] = f"// <{marker}>"
            restoration_stack.append(
                {
                    "marker": marker,
                    "fragment": line,
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
            fragment = line[col:end]  # 宏调用原文（含反引号与实参）
            if not body:
                # 空 body 宏：行内注释锚（marker 唯一，还原精确）
                marker = make_marker("macro", _next_macro_seq())
                parts[col:end] = f"/*<{marker}>*/"
                forward_entries.append(
                    {
                        "marker": marker,
                        "fragment": fragment,
                        "mode": "inline",
                        "kind": "macro",
                        "is_func": is_func,
                    }
                )
                continue
            token = f"tpc_marker_{_next_macro_seq()}"
            parts[col:end] = token
            forward_entries.append(
                {
                    "marker": token,
                    "fragment": fragment,
                    "mode": "token",
                    "kind": "macro",
                    "is_func": is_func,
                }
            )
        restoration_stack.extend(reversed(forward_entries))
        lines[line_no - 1] = "".join(parts)

    return "\n".join(lines), restoration_stack
