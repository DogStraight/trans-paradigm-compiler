"""Macro expansion — strip directives, expand `` `NAME `` references.

Pipeline: scan_directives() → expand_tokens() → Lexer
Both operate on pure text, no token dependency.

指令处理由 primitives/registry.py 的注册表分发，新增指令不修改本文件。
Doc: preprocessor/README.md
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any
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
from .primitives.ifdef import condition_syntax, outer_active
from ._bridge import make_marker
from ._markers import inline_marker, line_marker
from . import macro_expand, macro_timeline
from .macro_policy import (
    MODE_INLINE,
    MODE_LINE,
    MODE_SPLICE,
    load_macro_policy,
    plan_macro,
)
from .macro_shape import (
    load_macro_call_args,
    load_macro_call_suffix,
    load_macro_operators,
    load_macro_shapes,
    macro_keywords,
)

# ── 配置需求（来自 tpc.toml） ──────────────────────────
# preprocessor.macro_config 由 preprocessor/macro_shape.py 读取（形态声明；
# 本文件按 rules_dir 解析后交给它，不再自带一份声明）。

# preprocessor.expand
#   #sym:config = [expand]
#   格式: dict — { max_iterations: int }（用尽 → RuntimeWarning + 保留未展开文本）
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

#: 跨行实参收集的**前瞻上限**（行数）：未闭合调用最多向后拼这么多行，
#: 超限/EOF 仍不配平 ⇒ 按"未闭合调用"原样保留（既有边界，不把整文件拼进来）。
_MAX_JOINED_LINES = 256
#: 跨行实参收集的**前瞻上限**（字符数）：防"未闭合调用在后缀里拖全文件"的
#: 二次代价；超限同样按未闭合调用原样保留（不部分消费）。
_MAX_JOINED_CHARS = 8192


def continuation_character() -> str:
    """行拼接字符（语言包 `[continuation].character`；默认 `\\`）。"""
    return str(_continuation_cfg.get("character", "\\") or "\\")


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
    """include 指令配置（语言包声明 + 引擎默认）。

    `on_missing`：缺文件 / 循环 / 深度超限的处置——`warn`（默认，保留既有打印，
    verilog 不声明 ⇒ 零变化）或 `error`（结构化诊断，由管线转成受控错误）。
    `max_depth`：嵌套深度上限（未声明 = 不限）。
    默认值只在引擎侧此处一处；**用哪种策略由语言包声明**（引擎不写死语言知识）。
    """
    cfg: dict = {"on_missing": "warn"}
    cfg.update(_directives_cfg.get("include", {}))
    policy = cfg.get("on_missing")
    if policy not in ("warn", "error"):
        raise ConfigError(
            f"[preprocessor.directives.include] on_missing 非法：{policy!r}"
            "（只能是 'warn' 或 'error'）"
        )
    max_depth = cfg.get("max_depth")
    if max_depth is not None and (
        not isinstance(max_depth, int) or max_depth <= 0
    ):
        raise ConfigError(
            f"[preprocessor.directives.include] max_depth 非法：{max_depth!r}"
            "（需为正整数，或省略表示不限）"
        )
    return cfg


def directive_handlers() -> dict[str, dict]:
    """当前加载语言的 `[preprocessor.directives]`（指令关键字 → 处理器配置）。

    linter 阶段的形式化宏语法检查用它判定"哪些关键字是 define"；与
    `scan_directives` 读同一份声明（单一来源）。
    """
    return {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in _directives_cfg.items()
    }


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


def _load_directive_config(rules_dir: str) -> dict[str, dict]:
    """按语言包解析 `[directive_handlers]`（per-dir，与全局 loaded 配置解耦）。

    用途：条件指令关键字集合（`if` / `elif` 等由语言包显式声明绑定到引擎 op；
    未声明的语言包 —— 如 verilog —— 不把该关键字当指令）。
    ConfigRegistry.resolve 自带缓存（同一 rules_dir 只解析一次）。
    """
    from core.config_registry import ConfigRegistry

    resolved = ConfigRegistry.resolve(
        rules_dir, plugins_dir=os.path.join(rules_dir, "plugins")
    )
    raw = resolved.get("preprocessor.directives", {})
    if not isinstance(raw, dict):
        raise ConfigError(
            f"[preprocessor.directives] 须是表（得到 {type(raw).__name__}）"
        )
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _load_config(rules_dir: str) -> tuple[str, set[str]]:
    """宏形态声明 → (前缀文本, 指令名集合)。

    两者都从语言包 `[macro_recognition]` 的**形态生产式**推导（前缀 token 名 →
    符号文本；指令候选名 → 去 `macro.` 前缀的关键字）——前缀不在引擎里硬编码
    （解析见 preprocessor/macro_shape.py）。

    指令名集合 = 形态候选 ∪ 已注册原语名 ∪ **语言包 `[directive_handlers]` 声明的键**
    （后者是"语言声明了哪些指令关键字/绑定哪个 op"的声明面；如 C 的 `if` / `elif`）。

    按 rules_dir 解析该语言包的声明（与 `Lexer(rules_dir=...)` 同源），不复用
    全局已加载配置：同进程切语言时不串味（c4 无宏形态 → 空前缀 + 空指令集）。
    """
    shapes = load_macro_shapes(rules_dir=rules_dir)
    directive = shapes.get("directive")
    prefix = directive.prefix if directive is not None else ""
    configured = set(macro_keywords(directive)) if directive is not None else set()
    # 已注册的指令处理器名也算指令：未加载配置时也能区分"指令行 vs 行首宏调用"
    directives = (
        configured | set(list_primitives()) | set(_load_directive_config(rules_dir))
    )
    return prefix, directives


def _is_ifdef_active(ctx: dict) -> bool:
    """检查当前行是否在活跃的条件分支内（整条栈链都活跃才算）。

    单一实现在 `primitives/ifdef.py::outer_active`（条件块机制共用）。
    """
    return outer_active(ctx)


def _load_call_prefix(rules_dir: str) -> str | None:
    """**调用**形态前缀（三态；`_load_config` 只管 directive，不重复读配置）。

    `None` = 未声明 call 形态（永不匹配；c4 现状）；`""` = 显式无前缀
    （C 的裸标识符调用）；非空 = 前缀文本（verilog 的 `` ` ``）。
    """
    call = load_macro_shapes(rules_dir=rules_dir).get("call")
    return call.prefix if call is not None else None


def _build_macro_re(prefix: str | None, macro_names=()) -> re.Pattern:
    """宏调用正则（**三态**）。

    - `None`：未声明调用形态 ⇒ 永不匹配（该语言无宏调用面）；
    - `""`：**显式无前缀**（裸标识符调用）⇒ 正则由**宏表名字**编译 `(F|G|…)`
      （未定义的名字根本不进匹配；不是"看形态就认宏"）；
    - 非空：前缀 + 名字（名字用引擎级 `IDENT_RE`，与 lexer 同源）。
    """
    if prefix is None:
        return re.compile(r"(?!)")
    if prefix == "":
        # 名字按**长度降序**交替：`AB` 不被 `A` 抢先命中（有前缀关系的宏名必中）
        names = sorted({n for n in macro_names if n}, key=len, reverse=True)
        if not names:
            return re.compile(r"(?!)")
        alt = "|".join(re.escape(n) for n in names)
        return re.compile(rf"({alt})")
    return re.compile(re.escape(prefix) + f"({IDENT_RE.pattern})")


def _is_ident_char(ch: str) -> bool:
    """`ch` 是否标识符字符（**从 `IDENT_RE` 派生**，不另写字符类）。

    起始字符 = `IDENT_RE` 直接匹配；续接字符 = `IDENT_RE` 匹配 `"a"+ch`
    ⇒ 标识符口径只有 `core.token_protocol.IDENT_RE` 一个来源。
    """
    return bool(IDENT_RE.fullmatch(ch)) or bool(IDENT_RE.fullmatch("a" + ch))


# ── 纯文本展开（新方案）──


def _emit_output_line(
    ctx: dict, stack: list, jno: int | None, text: str
) -> None:
    """把一行写进当前输出位置：条件栈内归栈顶分支，栈外归顶层 clean 行。

    include 内容必须与**本指令的 marker 行**同一归属，且排在 marker 之后
    （C 语义：`#include` 行在前、被包含内容随后；渲染按 clean 行序恢复
    `#include` 原文）。无当前分支（块边界）时丢弃——与 `_append_to_branch`
    既有语义一致。
    """
    if stack:
        branch = stack[-1].get("cur_branch")
        if branch is not None:
            branch["lines"].append((jno, text))
        return
    ctx["_inject_lines"].append((jno, text))


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
    seq_box = ctx["_seq_box"]
    seq = seq_box[0]
    seq_box[0] = seq + 1
    marker = f"tpc:directive:{seq}"
    placeholder = line_marker(syntax, marker)
    ctx.setdefault("_directive_placeholders", {})[marker] = line
    _emit_output_line(ctx, stack, jno, placeholder)


def scan_directives(
    source: str,
    rules_dir: str,
    *,
    source_path: str | None = None,
    _include_stack: set[str] | None = None,
    search_dirs: list[str] | None = None,
    predefined: dict[str, str] | None = None,
    undefine: set[str] | None = None,
    seq_box: list[int] | None = None,
    out_diags: list[dict] | None = None,
    out_macro_events: list[dict] | None = None,
    out_include_edges: list[tuple[str, str]] | None = None,
    preexpand_includes: bool = True,
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
        out_macro_events（可选出参）：宏**定义/取消事件**列表，每项
                          `{line: 原始源行号, name, params: list | None}`（None =
                          非函数宏，含 `#undef` 与对象宏定义）；顺序 = 源码序。
                          供 `preprocessor.macro_timeline` 取调用点时点状态——
                          展开器用最终宏表，检查侧的顺序语义靠它修正。
    """
    prefix, directives_set = _load_config(rules_dir)
    ctx = _build_scan_ctx(
        rules_dir,
        source_path,
        search_dirs,
        predefined,
        undefine,
        _include_stack,
        seq_box,
    )
    ctx["_preexpand_includes"] = bool(preexpand_includes)

    # ── 预合并延续行（反斜杠折行）──
    # 账本：每条输出行携带其**原始行号**（行与行号成对入列表）——clean 行数
    # 与原始行数不同（条件压缩/续行合并），行映射只能逐行记账，不能事后对齐。
    source, join_map = _join_continuation_lines(source)
    _scan_lines(source.split("\n"), ctx, prefix, directives_set, rules_dir, join_map)
    _report_unclosed_conditions(ctx)

    result = _collect_scan_result(ctx, join_map)
    if out_diags is not None:
        # 结构化诊断由调用方持有（管线转成 `preprocessor_errors`）——返回元组不变
        out_diags.extend(ctx.get("_include_diags", []))
        out_diags.extend(ctx.get("_cond_diags", []))
    if out_macro_events is not None:
        out_macro_events.extend(ctx.get("_macro_events", []))
    if out_include_edges is not None:
        # 单元图包含边（块 5）：`(source, target)` 二元组——**不带 kind**；kind 归语言包
        # （`[[unit_graph.edges]] kind + from`），本阶段只是 `preprocessor.include_edges` 通道。
        out_include_edges.extend(ctx.get("_include_edges", []))
    # 宏体**不再预展开**（③）：`macro_defs` 保持原始体，替换文本由调用点用
    # `macro_expand.expand_text(..., hideset={name})` 现算 ⇒ 消除"扫描期预展开 +
    # 调用点正则插入"的双算法路径（P0-8/P0-10/P2-1 同一根因）。
    return result


def _report_unclosed_conditions(ctx: dict) -> None:
    """扫描结束仍有未收的条件块 → 诊断（仅声明 `[condition]` 的语言包；C 标准要求）。

    未闭合块即使处于 inactive 分支也报（gcc 同：宁可多报配对错误）。
    """
    if condition_syntax(ctx) is None:
        return
    for frame in ctx.get("_ifdef_stack", []):
        block = frame["block"]
        start = next((n for n, _ in block["boundary_lines"] if n is not None), None)
        where = f"（起始 L{start}）" if start is not None else ""
        ctx.setdefault("_cond_diags", []).append(
            {
                "kind": "condition-balance",
                "message": f"未闭合的条件块{where}：缺少匹配的收尾指令",
                "line": start,
                "column": 1,
            }
        )


def _build_scan_ctx(
    rules_dir: str,
    source_path: str | None,
    search_dirs: list[str] | None,
    predefined: dict[str, str] | None,
    undefine: set[str] | None,
    include_stack: set[str] | None,
    seq_box: list[int] | None = None,
) -> dict:
    """扫描会话上下文：宏表 + 条件栈/占位序号 + 路径与配置（handler 共享）。

    搜索路径：CLI 传入的 search_dirs 优先，合并配置中的 search_dirs。
    带参宏的实参形态（语言包 `[macro_recognition]` 的 call_args / arg_separator）：
    定义侧形参表与展开侧实参表共用它（引擎不硬编码 `(` / `,`）。
    `seq_box`（单元素列表 = 共享计数器）：**嵌套 include 的递归扫描必须与宿主共用**
    一个 marker 序号源——各自从 0 起会撞号（clean 流出现两个 `tpc:directive:0`），
    使 `restore_anchors` 还原错位；未传则新建（顶层扫描）。
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
        # 指令 marker 序号源（单元素 list = 可共享的计数器）：嵌套 include 递归
        # 扫描传同一个 box，避免与宿主撞号（`tpc:directive:N` 必须全局唯一）。
        "_seq_box": seq_box if seq_box is not None else [0],
        "_directive_placeholders": {},
        # include 问题诊断（按语言包 `on_missing` 策略：error 时记此，warn 时打印）
        "_include_diags": [],
        # 单元图包含边（块 5）：(本文件, 被包含文件)——kind 由引擎能力面映射
        "_include_edges": [],
        # 当前扫描文件（包含边的 source；嵌套子扫描传子文件路径）
        "source_path": source_path,
        # 宏定义/取消事件（原始源行号 + 形参表 + 宏体/op）：两用面——
        # `macro_timeline` 取调用点可见形参表；展开器（`expand_tokens(events=)`）
        # 按定义时间线维护可见宏集。
        "_macro_events": [],
        # 扫描期可见宏集（include 预展开/子扫描继承用；按源码序更新，inactive
        # 分支不执行）。predefined（含父文件传入的 include 点快照）作为起点。
        "_active_defs": dict(predefined) if predefined else {},
        "_active_funcs": {},
        # include 内容是否在包含点用"当时可见宏集"预展开（parse_raw 模式关）
        "_preexpand_includes": True,
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
        # 指令关键字 → op 绑定（per-dir 解析；条件指令 `if` / `elif` 的声明面）
        "_directive_config": _load_directive_config(rules_dir),
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
    lines: list[str],
    ctx: dict,
    prefix: str,
    directives_set: set[str],
    rules_dir: str,
    join_map: list,
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
        # 行拼接账本：本逻辑行的**原始源行号**（段首；定义/取消事件按原始源坐标记）
        ctx["_cur_raw_line"] = (
            join_map[jno - 1] if 1 <= jno <= len(join_map) else jno
        )
        ctx["_cur_line_indent"] = len(line) - len(line.lstrip())
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
        _emit_output_line(ctx, stack, jno, line)
    elif _is_ifdef_active(ctx):
        _emit_output_line(ctx, stack, jno, line)


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

    handler_cfg = ctx.get("_directive_config", {}).get(directive_name, {})
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
        # 活跃分支内：**先写本行 marker，再执行 handler**——include handler 把
        # 被包含内容追加在同一归属位，顺序 = 指令行 → 内容（C 语义；此前先执行
        # handler 会让内容行排在 marker 前，渲染/行映射错位）。define/undef
        # 不产内容行，顺序无影响。
        _inject_directive_marker(ctx, stack, jno, line, syntax)
        _invoke_directive(op, stripped, prefix, directive_name, ctx)
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
    #: 掩码用（字符串/字符字面量定界符 + 转义；来自 token 表 `[string]`）
    string_delimiters: tuple[str, ...] = ()
    escape: str | None = None
    #: 裸标识符调用（call 前缀为 `""`）：匹配后需整词判定（边界从 `IDENT_RE` 派生）
    bare_call: bool = False
    #: 宏算子（语言包声明；替参 `#`/`##`/变参语义用）
    operators: Any = None
    #: **调用**形态前缀（三态：None 未声明 / "" 裸调用 / 非空前缀）——体展开用
    call_prefix: str | None = ""
    restoration_stack: list[dict] = field(default_factory=list)
    regions_by_line: dict[int, list[dict]] = field(default_factory=dict)
    seq: int = 0
    #: 函数宏**调用点事实**收集器（调用方传 `out_invocations` 才启用；None =
    #: 不记录）。每项 = `{name, slots, single_empty, params, line, column}`，
    #: 行/列是**本函数输入文本**（clean 源）坐标——调用方负责回源到原始源
    #: （`clean_line_map` / `clean_to_raw`），引擎不猜语言坐标。
    invocations: list[dict] | None = None

    def next_seq(self) -> int:
        """锚序号（自增；`make_marker` 的唯一性来源）。"""
        self.seq += 1
        return self.seq


def expand_tokens(
    source: str,
    macro_defs: dict[str, str],
    *,
    rules_dir: str,
    prefix: str | None = None,
    func_macros: dict[str, list[str]] | None = None,
    include_line_flags: list[bool] | None = None,
    out_include_regions: list[dict] | None = None,
    out_invocations: list[dict] | None = None,
    events: list[dict] | None = None,
    clean_to_raw: list[int | None] | None = None,
    base_macros: dict[str, str] | None = None,
    base_funcs: dict[str, list[str]] | None = None,
) -> tuple[str, list[dict], list[dict], list[int]]:
    """在源码文本中展开宏调用（纯文本层），并注册统一锚 / 宏区间表。

    用正则搜索宏调用（前缀 + 名字，或**显式无前缀**时的裸标识符）；向左扫同步词，
    记录位置后替换宏体。带参宏（func_macros 中登记的名字）识别调用并做形参替换。
    不再依赖 Token 流或 Lexer。

    `prefix` 缺省 `None` = **从语言包 `[macro_recognition]` 的 call 形态推导**
    （`_load_config` 的 kind 分派；`None` 调用形态 ⇒ 永不匹配）；显式传值可覆盖。

    rules_dir：语言包目录——锚以注释形态穿过管线，标点从声明取
    （`lexer/comment_syntax.py`，引擎不认识 `//` / `/* */`）。

    处置由**语言包策略**决定（`[capabilities] macro_policy`；未声明 → 默认 `splice`）。
    引擎执行的处置（机制面，见 macro_policy.py；与铺条目 mode 同词）：
      splice   宏体铺进流（+ 宏区间；末行含行注释时补换行，见 _splice_body）
      line     整行占位（行注释锚），source_text = 整行原文
      inline   行内注释锚（原位回插宏调用原文）

    **定义时间线**（`events` 非空时启用）：事件 = scan 期
    `_macro_events`（`{line: 原始行, name, op: define|undef, body, params}`）。
    逐行按 `clean_to_raw` 求原始行，取"`line < 当前原始行` 的最后状态"重建可见宏集；
    `clean_to_raw[i] is None`（include 拼接行）**跳过展开**——这些行已在扫描期用
    include 包含点当时的可见宏集预展开（`_preexpand_includes`），再展开会二次替换。
    `events=None` ⇒ 旧行为（全文件最终宏表；测试/旧调用方）。`base_macros`/
    `base_funcs` 为时间线起点（缺省 = 最终表中**无同名事件**的项，即 predefined/初始态）。

    Returns: (expanded_source, restoration_stack, macro_regions, line_map)
        line_map — **展开后行号（1-based）→ 源（clean）行号**：诊断回源用。
            逐行就地替换 → 输出行数只可能因宏体含换行而增加，一行源行对应
            一串连续输出行，故 list[int] 足够（无需完整区间表）。
        restoration_stack — 统一锚列表（`line`/`inline` 置位用），每项含
            marker/source_text/mode。
        macro_regions — **宏区间表**：每条"宏体被铺进文本"的调用一项，含它在
            **源文本**里的区间（`src_line`/`src_col`/`src_end_line`/`src_end_col`；
            跨行调用时 src_end_line 是闭括号所在行、src_end_col 是该行列）与它在
            **展开结果**里的字符区间（`offset`/`end_offset`），以及 `name`/
            `source_text`（宏调用原文，跨行时为多行原文段）/`body`（实际铺进的内容；
            宏体末行含行注释时末尾补了一个换行，见下）。
            它是外层处理宏的单一事实源（ADR-0017 决策 3）：定位"哪些内容来自
            哪条宏"→ 渲染侧 raw 拼接、诊断宏归因都靠它。
        out_invocations — 可选**函数宏调用点事实**收集器（传 list 才记录；None =
            零开销不记）。每项 = `{name, slots, single_empty, params, line, column}`：
            行/列是本函数输入文本（clean 源）坐标，`params` 是该调用点的宏表形参表
            （含语言包声明的变参占位），调用方负责回源到原始源坐标。引擎只记事实，
            不判定"实参个数对不对"（语义判定归语言包 check 族）。

    **跨行调用**（循环 #24；C 预处理 token 不区分换行）：函数宏的实参列表、或
    名字与开括号可跨物理行。展开保持**行数不变**：首行 = 行首~调用列 + 宏体，
    中间被吞行 = 空串，尾行 = 闭括号后原文（换行 = 预处理空白）⇒ `out_to_src`
    仍按"clean 源行 → 输出行"对齐；区域 `source_text` = 完整跨行原文。仅
    **splice** 处置支持（line/inline 保持旧行为不展开）。
    """
    if prefix is None:
        # 调用前缀从语言包 call 形态推导（kind 分派；不读第二份配置）
        prefix = _load_call_prefix(rules_dir)
    # 时间线模式下，宏名集合 = 最终表 ∪ 事件里出现过的名字（`#undef` 后最终表
    # 已无该名，但定义前/定义段的文本仍需按"当时可见"匹配 → 名字必须进正则）
    _names = set(macro_defs.keys())
    if events:
        _names.update(
            str(e.get("name") or "")
            for e in events
            if e.get("op") != "undef" and e.get("name")
        )
    _MACRO_RE = _build_macro_re(prefix, _names)
    func_macros = func_macros or {}
    # 实参形态与后随字面量后缀都由语言包声明（引擎不硬编码 `(` / `,` / `'d`）
    call_args = load_macro_call_args(rules_dir=rules_dir)
    suffix_re = load_macro_call_suffix(rules_dir=rules_dir)
    operators = load_macro_operators(rules_dir=rules_dir)
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
        string_delimiters=operators.string_delimiters,
        escape=operators.escape,
        bare_call=prefix == "",
        call_prefix=prefix,
        operators=operators,
        lines=source.split("\n"),
        invocations=out_invocations,
    )
    lines = ctx.lines
    # 掩码**整段一次性**算再落到各行（行内区间）：逐行重算会漏掉跨行块注释的
    # 续行（续行没有起始定界符）⇒ 续行里的宏名被误当调用展开（P1-3）。
    line_masks = _line_masks(
        macro_expand.mask_spans(
            source, ctx.string_delimiters, ctx.escape, ctx.syntax
        ),
        lines,
    )

    # ── 定义时间线（可选；events=None = 旧行为）──
    timeline = events is not None
    timeline_events: list[dict] = []
    tl_idx = 0
    active_defs: dict[str, str] = {}
    active_funcs: dict[str, list[str]] = {}
    if timeline:
        timeline_events = sorted(
            events, key=lambda e: int(e.get("line") or 0)
        )
        ev_names = {str(e.get("name") or "") for e in timeline_events}
        base_d = base_macros if base_macros is not None else macro_defs
        base_f = base_funcs if base_funcs is not None else func_macros
        active_defs = {
            str(n): str(b) for n, b in base_d.items() if str(n) not in ev_names
        }
        active_funcs = {
            str(n): list(p) for n, p in base_f.items() if str(n) not in ev_names
        }

    for line_no, line in enumerate(lines, 1):
        if timeline:
            raw = (
                clean_to_raw[line_no - 1]
                if clean_to_raw is not None and 1 <= line_no <= len(clean_to_raw)
                else line_no
            )
            if raw is None:
                # include 内容行：扫描期已按包含点可见宏集预展开（见上）
                continue
            while (
                tl_idx < len(timeline_events)
                and int(timeline_events[tl_idx].get("line") or 0) < int(raw)
            ):
                ev = timeline_events[tl_idx]
                tl_idx += 1
                name = str(ev.get("name") or "")
                if not name:
                    continue
                if ev.get("op") == "undef":
                    active_defs.pop(name, None)
                    active_funcs.pop(name, None)
                    continue
                active_defs[name] = str(ev.get("body") or "")
                params = ev.get("params")
                if isinstance(params, list):
                    active_funcs[name] = [str(x) for x in params]
                else:
                    active_funcs.pop(name, None)
            ctx.macro_defs = active_defs
            ctx.func_macros = active_funcs
        macro_matches = _collect_macro_matches(
            ctx, line, line_masks[line_no - 1], line_no
        )
        if not macro_matches:
            continue

        # ── 处置方案（引擎给事实、语言包策略给枚举；见 macro_policy.py）──
        # `only_call_in_line` 按**旧视野**（不含跨行匹配）计：line/inline 处置的
        # 行为与跨行支持落地前一致（跨行匹配只在 splice 下生效）
        visible = sum(1 for mm in macro_matches if mm[8] is None)
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
                    visible == 1,
                ),
            )
            for col, end, body, name, is_func, args_text, _slots, _empty, _cross in macro_matches
        ]
        # 跨行调用只在 splice 处置下展开；line/inline 保持旧行为（原样不展开）
        kept = [
            (mm, plan)
            for mm, plan in zip(macro_matches, plans)
            if mm[8] is None or plan["mode"] == MODE_SPLICE
        ]
        # 同行还有 MODE_LINE（整行占位）处置的调用 ⇒ 整行占位语义与跨行冲突：
        # 退化为"不展开跨行调用"（旧行为），单行匹配仍走既有 `_try_line_mode`
        if any(
            mm[8] is not None and plan["mode"] == MODE_SPLICE
            for mm, plan in kept
        ) and any(plan["mode"] == MODE_LINE for mm, plan in kept if mm[8] is None):
            kept = [(mm, plan) for mm, plan in kept if mm[8] is None]
        macro_matches = [mm for mm, _ in kept]
        plans = [plan for _, plan in kept]
        if not macro_matches:
            continue
        if any(mm[8] is not None for mm in macro_matches):
            _apply_cross_line(ctx, line_no, line, macro_matches, plans, line_masks)
            continue

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

    if out_include_regions is not None and include_line_flags is not None:
        # include 内容行 → 展开文本字符区间（渲染前剪枝用；分析面照常消费内容）
        out_include_regions.extend(
            _include_regions_from_flags(include_line_flags, lines)
        )

    return(
        "\n".join(lines), ctx.restoration_stack, macro_regions, out_to_src
    )


def _include_regions_from_flags(
    flags: list[bool], lines: list[str]
) -> list[dict[str, int]]:
    """include 内容行（逐行布尔）→ 展开文本的字符区间表（连续行合并）。

    只供**渲染前剪枝**用：分析面（lint/analyze）照常消费内容，渲染面按区间摘节点。
    区间按"一行在展开文本里的字符跨度"算——宏体换行会改变输出行数，但一个输入行
    的跨度覆盖它展开出的所有输出行（因此不受影响）。
    """
    if len(lines) != len(flags):
        flags = flags[: len(lines)]
    joined = "\n".join(lines)
    counts = [ln.count("\n") + 1 for ln in lines]
    line_char: list[int] = []
    pos = 0
    for ln in joined.split("\n"):
        line_char.append(pos)
        pos += len(ln) + 1
    starts: list[int] = []
    acc = 0
    for i in range(len(lines)):
        starts.append(line_char[acc] if acc < len(line_char) else len(joined))
        acc += counts[i]
    regions: list[dict[str, int]] = []
    run_start: int | None = None
    for i, flag in enumerate(flags):
        if flag:
            if run_start is None:
                run_start = starts[i]
        elif run_start is not None:
            regions.append({"offset": run_start, "end_offset": starts[i] - 1})
            run_start = None
    if run_start is not None:
        regions.append({"offset": run_start, "end_offset": len(joined)})
    return regions


def _raw_variadic_for(
    ctx: "_MacroExpandCtx",
    name: str,
    args_text: str,
    call_args: "macro_expand.MacroCallArgs",
) -> str | None:
    """`#__VA_ARGS__` 用的**变参区原文**（P1-1）；非变参/宏体不用到 → None。"""
    operators = ctx.operators
    if operators is None or operators.variadic is None:
        return None
    if "..." not in ctx.func_macros.get(name, []):
        return None
    named = [p for p in ctx.func_macros[name] if p != "..."]
    return macro_expand.variadic_raw_text(
        args_text, call_args, len(named), operators, ctx.syntax
    )


def _collect_call_args(
    ctx: "_MacroExpandCtx", line: str, line_no: int, start: int
) -> tuple[list[list], dict] | None:
    """名字之后收实参：**单行优先**，未闭合则逐行前瞻拼接（跳空白/注释同前）。

    返回 `(args, info)`；非调用形态（无开括号 / 到前瞻上限仍未配平）→ None。
    info 键：`call_text`（名字之后到闭括号的原文段，跨行用 `\\n` 连接）、
    `close_idx`（单行时闭括号后的行内下标；跨行为 None）、`cross`、
    `last_line`/`close_col`/`last_after`（闭括号所在行 1-based、行内列、其后原文）。

    跨行收集原理：`mask_spans` 对含换行的文本本就正确（行注释止于换行、块注释
    跨行；匹配起点不在掩码内 ⇒ 起点后掩码态为 plain），故直接对
    `首行后缀 + "\\n" + 后续行…` 调 `collect_args_tokens` 即可，无需第二套 tokenizer。
    """
    suffix = line[start:]
    got = macro_expand.collect_args_tokens(
        suffix, ctx.call_args, ctx.operators, ctx.syntax
    )
    if got is not None:
        args, consumed = got
        end = start + consumed
        return args, {
            "call_text": line[start:end],
            "close_idx": end,
            "cross": False,
            "last_line": line_no,
            "close_col": end - 1,
            "last_after": line[end:],
        }
    # 提前止损：名字后第一个显著 token 不是开括号 ⇒ 再拼行也不可能是调用
    first = macro_expand.first_significant_token(
        suffix, ctx.operators, ctx.syntax
    )
    if first is not None and first != ctx.call_args.open:
        return None
    joined = suffix
    segs = [suffix]
    for ln in range(line_no + 1, min(len(ctx.lines), line_no + _MAX_JOINED_LINES) + 1):
        nxt = ctx.lines[ln - 1]
        if len(joined) + 1 + len(nxt) > _MAX_JOINED_CHARS:
            return None  # 字符上限：不展开（不部分消费）
        segs.append(nxt)
        joined = joined + "\n" + nxt
        got = macro_expand.collect_args_tokens(
            joined, ctx.call_args, ctx.operators, ctx.syntax
        )
        if got is None:
            # 提前止损：拼上来的文本里第一个显著 token 已经不是开括号 ⇒
            # 再往后拼也不可能成为调用（中间 token 不会消失），O(1) 退出。
            first = macro_expand.first_significant_token(
                joined, ctx.operators, ctx.syntax
            )
            if first is not None and first != ctx.call_args.open:
                return None
            continue
        args, consumed = got
        offset = consumed - 1 - len(segs[0])  # 闭括号在后续段中的偏移（先减首行）
        for k in range(1, len(segs)):
            offset -= 1  # 段间换行符占 1 字符
            if offset < len(segs[k]):
                return args, {
                    "call_text": joined[:consumed],
                    "close_idx": None,
                    "cross": True,
                    "last_line": line_no + k,
                    "close_col": offset,
                    "last_after": segs[k][offset + 1 :],
                }
            offset -= len(segs[k])
    return None


def _match_one(
    ctx: "_MacroExpandCtx", line: str, m, line_no: int = 0
) -> tuple[int, str, str, bool, str, int, bool, dict | None] | None:
    """单个正则命中 → `(end, body, name, is_func, args_text, slots, single_empty,
    cross)`；不可展开 → None。

    **函数宏**（名字在 `func_macros`）：名字后允许**空白/注释/换行**再接 `(`；
    实参切分走 **token 级** `collect_args_tokens`（掩码内逗号/括号不是分隔符）；
    单行未闭合时**逐行前瞻**（`_collect_call_args`，上限 `_MAX_JOINED_LINES`）。
    名字后**没有 `(`** ⇒ **不展开**（标准：函数的宏名不调用就不替换，不得回退成
    对象宏）。
    对象宏：按宏表替换（无参）；`slots`/`single_empty` 恒 0/False（无实参表）。
    `slots` = 实参槽数（顶层分隔符数 + 1；`F()` 也是 1 槽）；
    `single_empty` = 仅当 `slots == 1` 时该槽是否**不含预处理 token**（空白/注释）。
    两者都是**通用事实**：个数合不合规由语言包 check 族判（引擎不判）。

    **接缝重扫**（C 标准 §6.10.3.4：替换列表连同其余源码一起重扫描）：宏体
    展开后的**最后一个函数宏名**可能与源码后续 `(...)` 合成新调用（`#define g f`
    + `g(2)` → `f(2)` 再展开）⇒ 交给 `_rescan_junction`，消费的源码字符并入
    `end`。`line_no` 只用于重扫调用的**调用点事实**记录。

    **跨行调用**（A1 边界②落地）：实参跨行收集成功时 `cross` = 闭括号所在行
    信息（`{"last_line", "close_col", "call_text", "last_after"}`）、`end` 取
    `len(line)`（消费本行余下文本）；接缝重扫/宏链扩展**不跨行**（嵌套边界）。
    """
    name = m.group(1)
    if ctx.call_args is not None and name in ctx.func_macros:
        collected = _collect_call_args(ctx, line, line_no, m.end())
        if collected is None:
            return None  # 函数宏名未调用（P0-6/7；不得回退对象宏）
        args, call = collected
        arg_text = call["call_text"]
        body_toks = macro_expand.substitute_call_tokens_tokens(
            name,
            args,
            ctx.macro_defs,
            ctx.func_macros,
            ctx.call_args,
            operators=ctx.operators,
            syntax=ctx.syntax,
            raw_args=_raw_variadic_for(ctx, name, arg_text, ctx.call_args),
            prefix=ctx.call_prefix if ctx.call_prefix is not None else "",
        )
        slots = len(args)
        single_empty = slots == 1 and macro_expand.arg_tokens_blank(
            args[0], ctx.syntax
        )
        if call["cross"]:
            # 跨行：不接接缝/宏链（嵌套边界；行映射按"首行展开 + 中间行置空"）
            return (
                len(line),
                macro_expand.join(body_toks),
                name,
                True,
                arg_text,
                slots,
                single_empty,
                {
                    "last_line": call["last_line"],
                    "close_col": call["close_col"],
                    "call_text": line[m.start() : m.end()] + arg_text,
                    "last_after": call["last_after"],
                },
            )
        end = call["close_idx"]
        body_toks, end = _rescan_junction(
            ctx, body_toks, line, end, line_no, m.start()
        )
        # 接缝消费后再做宏链扩展（后缀/相邻宏调用并入同一区间；顺序 = 接缝→链）
        end = _extend_macro_chain(line, end, ctx.macro_re, ctx.suffix_re)
        return (
            end,
            macro_expand.join(body_toks),
            name,
            True,
            arg_text,
            slots,
            single_empty,
            None,
        )
    body = ctx.macro_defs.get(name)
    if body is None:
        return None
    # 对象宏：替换文本由 hideset 展开器**现算**（初始 hideset={name} 防自递归；
    # 体里再出现的宏调用在此一并展开 ⇒ P0-8/P0-10/P2-1 同一根因消解）
    body_toks = macro_expand.expand_text_tokens(
        body,
        ctx.macro_defs,
        ctx.func_macros,
        ctx.call_args,
        prefix=ctx.call_prefix if ctx.call_prefix is not None else "",
        budget=int(_get_expand_config().get("max_iterations", 128)),
        operators=ctx.operators,
        syntax=ctx.syntax,
        hideset=frozenset({name}),
    )
    end = m.end()
    body_toks, end = _rescan_junction(ctx, body_toks, line, end, line_no, m.start())
    end = _extend_macro_chain(line, end, ctx.macro_re, ctx.suffix_re)
    return end, macro_expand.join(body_toks), name, False, "", 0, False, None


def _last_meaningful(body_toks: list) -> int:
    """宏体里最后一个有意义 token 下标（跳纯空白；无 → -1）。"""
    i = len(body_toks) - 1
    while i >= 0 and not body_toks[i].text.strip():
        i -= 1
    return i


def _junction_step(
    ctx: "_MacroExpandCtx",
    body_toks: list,
    line: str,
    end: int,
    prefix: str,
) -> tuple[int, Any, list, int, int, list] | None:
    """识别一个可形成的接缝（**只识别不改写**）→ `(call_start, cand, args, after, consumed, rest_toks)`。

    条件与既有接缝语义一致：宏体最后一个有意义 token 是**可展开的函数宏名**（前缀语言
    还要求其前是声明的调用前缀 token），源码后续（从 `end` 起）以实参开括号开始。
    返回 None = 不再形成接缝（或无法形成一次完整调用）。
    """
    li = _last_meaningful(body_toks)
    if li < 0:
        return None
    cand = body_toks[li]
    if cand.masked or not IDENT_RE.fullmatch(cand.text):
        return None
    if prefix:
        if li == 0 or body_toks[li - 1].text != prefix:
            return None
        call_start = li - 1  # 前缀 token 随调用一并消费
    else:
        call_start = li
    if cand.text not in ctx.macro_defs or cand.text in cand.hide:
        return None
    if cand.text not in ctx.func_macros or ctx.call_args is None:
        return None
    rest = line[end:]
    rest_toks = macro_expand.tokenize(
        rest,
        ctx.operators,
        macro_expand.mask_spans(rest, ctx.string_delimiters, ctx.escape, ctx.syntax),
    )
    got = macro_expand.collect_args_at(rest_toks, 0, ctx.call_args, ctx.syntax)
    if got is None:
        return None
    args, after = got
    consumed = sum(len(t.text) for t in rest_toks[:after])
    return call_start, cand, args, after, consumed, rest_toks


def _rescan_junction(
    ctx: "_MacroExpandCtx",
    body_toks: list,
    line: str,
    end: int,
    line_no: int,
    call_col: int,
) -> tuple[list, int]:
    """**接缝重扫**：宏体末尾的函数宏名 + 源码后续 `(...)` → 合成一次调用继续展开。

    标准依据（C99 §6.10.3.4p2）：宏替换后"替换列表**连同其余源码**一起重扫描"
    ⇒ `#define g f` 后 `g(2)` 里替换出的 `f` 与源码 `(2)` 在接缝处形成 `f(2)`，
    应继续展开（GCC 16.1.0 实测 `2 +1`）；`#define f(a) a*g` + `#define g(a) f(a)`
    + `f(2)(9)` ⇒ `2*9*g`。本函数只处理这一条接缝：宏体最后一个有意义 token 是
    **可展开的函数宏名**（前缀语言还要求其前是声明的调用前缀 token），且源码后续
    （跳空白/注释）以实参开括号开始。消费的源码字符并入该调用的 `end`——区域/锚/
    行映射**不新增机制**（输出行数不变）。循环到不再形成接缝；预算
    `max_iterations` 用尽时**发可见告警**（不静默保留未展开接缝）并停止。
    函数宏调用点事实照记（供语言包 check 族）。

    不处理：接缝重扫**不跨行**（宏体末名字 + 下一行 `(` 不接；跨行调用本身由
    `_match_one` 的跨行实参收集处理）；宏体**内部**的替换重扫已由
    `macro_expand` 的 hideset 引擎负责。
    """
    limit = int(_get_expand_config().get("max_iterations", 128))
    budget = limit
    prefix = ctx.call_prefix if ctx.call_prefix is not None else ""
    while True:
        step = _junction_step(ctx, body_toks, line, end, prefix)
        if step is None:
            break
        if budget <= 0:
            macro_expand.warn_budget_exhausted(limit, "接缝重扫")
            break
        budget -= 1
        call_start, cand, args, after, consumed, rest_toks = step
        # hideset 交集（Prosser）：调用区间各 token 的 hide 集交集 ∪ {宏名}
        hideset = cand.hide
        for arg in args:
            for t in arg:
                hideset = hideset & t.hide
        hideset = hideset & rest_toks[after - 1].hide
        named = [p for p in (ctx.func_macros.get(cand.text) or []) if p != "..."]
        rest = line[end:]
        expanded = macro_expand.substitute_call_tokens_tokens(
            cand.text,
            args,
            ctx.macro_defs,
            ctx.func_macros,
            ctx.call_args,
            operators=ctx.operators,
            syntax=ctx.syntax,
            raw_args=macro_expand.variadic_raw_text(
                rest[:consumed],
                ctx.call_args,
                len(named),
                ctx.operators,
                ctx.syntax,
            ),
            hideset=hideset,
            prefix=prefix,
        )
        if ctx.invocations is not None:
            ctx.invocations.append(
                {
                    "name": cand.text,
                    "slots": len(args),
                    "single_empty": len(args) == 1
                    and macro_expand.arg_tokens_blank(args[0], ctx.syntax),
                    "params": list(ctx.func_macros.get(cand.text, ())),
                    "line": line_no,
                    "column": call_col,
                }
            )
        body_toks = body_toks[:call_start] + expanded
        end += consumed
    return body_toks, end


def _line_masks(
    spans: list[tuple[int, int]], lines: list[str]
) -> list[list[tuple[int, int]]]:
    """整段掩码区间（源文本绝对偏移）→ 每行的行内掩码区间（左闭右开、裁到行界）。

    跨行块注释：首行有 `/*`、续行没有 ⇒ 续行的区间从行首开始（`max(a-offset, 0)`），
    这样续行里的宏名不再参与匹配（P1-3）。行序与 `lines` 一一对应。
    """
    result: list[list[tuple[int, int]]] = []
    offset = 0
    for line in lines:
        end = offset + len(line)
        result.append(
            [
                (max(a - offset, 0), min(b - offset, len(line)))
                for a, b in spans
                if a < end and b > offset
            ]
        )
        offset = end + 1  # 换行符占 1 字符（split("\n") 的口径）
    return result


def _collect_macro_matches(
    ctx: "_MacroExpandCtx",
    line: str,
    masks: list[tuple[int, int]] | None = None,
    line_no: int = 0,
) -> list[tuple]:
    """本行的宏调用（原起列, 原止列, 宏体, 名字, 是否带参, 实参文本, 实参槽数,
    单槽是否空）。

    `masks` = 该行的**行内**掩码区间（由整段源文本一次性算出，见 `_line_masks`）：
    跨行块注释的续行没有起始定界符，逐行重算会漏算 ⇒ 调用方必须传（P1-3）。
    缺省按本行现算（仅单行上下文用）。
    `line_no` = 本行在输入文本里的 1-based 行号——只用于**调用点事实**记录
    （`ctx.invocations`；函数宏调用成功识别时记一条），不参与展开。
    """
    matches: list[tuple] = []
    consumed_until = -1
    # 掩码：字符串/字符/行注释/块注释内的文本不参与宏匹配（与裸匹配同一扫描）
    spans = (
        masks
        if masks is not None
        else macro_expand.mask_spans(
            line, ctx.string_delimiters, ctx.escape, ctx.syntax
        )
    )

    def _masked(pos: int) -> bool:
        return any(a <= pos < b for a, b in spans)

    for m in ctx.macro_re.finditer(line):
        if m.start() < consumed_until:
            continue  # 已被前一个宏调用链吞噬（`W'd`RST 嵌套）
        if _masked(m.start()):
            continue  # 掩码区内（字面量/注释）不展开
        if ctx.bare_call and (
            (m.start() > 0 and _is_ident_char(line[m.start() - 1]))
            or (m.end() < len(line) and _is_ident_char(line[m.end()]))
        ):
            continue  # 裸调用须整词匹配（`FOOBAR` 不被 `FOO` 误伤）
        hit = _match_one(ctx, line, m, line_no)
        if hit is None:
            continue
        end, body, name, is_func, args_text, slots, single_empty, cross = hit
        if is_func and ctx.invocations is not None:
            ctx.invocations.append(
                {
                    "name": name,
                    "slots": slots,
                    "single_empty": single_empty,
                    "params": list(ctx.func_macros.get(name, ())),
                    "line": line_no,
                    "column": m.start(),
                }
            )
        consumed_until = max(consumed_until, end)
        matches.append(
            (m.start(), end, body, name, is_func, args_text, slots, single_empty,
             cross)
        )
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
    for (col, end, body, name, is_func, _args, _slots, _empty, _cross), plan in reversed(
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


def _shift_masks(
    masks: list[tuple[int, int]], shift: int
) -> list[tuple[int, int]]:
    """掩码区间左移 `shift` 字符并裁到新行界（跨行调用截断尾行用）。"""
    return [(max(0, a - shift), b - shift) for a, b in masks if b > shift]


def _apply_cross_line(
    ctx: "_MacroExpandCtx",
    line_no: int,
    line: str,
    matches: list[tuple],
    plans: list[dict],
    line_masks: list[list[tuple[int, int]]],
) -> None:
    """含**跨行调用**的行：splice 展开（行数不变）。

    接法（A1 边界②落地，保持行映射冻结面）：
    - 首行 = 行首~调用列 + 宏体（宏体可含换行 ⇒ 输出行数按既有 splice 口径增加）；
    - 中间被吞行 = 空串（行数不变 ⇒ `out_to_src` 仍按"clean 源行 → 输出行"对齐）；
    - 尾行 = 闭括号后原文（token 相邻关系由换行隔开，语义不变）。
    跨行调用**不接**接缝重扫/宏链扩展（嵌套边界）。尾行掩码按截断量左移，
    避免"被吞前缀的掩码偏移"误判尾行的字符串/注释。
    """
    parts = list(line)
    forward_entries: list[dict] = []
    line_regions: list[tuple] = []
    for (col, end, body, name, is_func, _args, _slots, _empty, cross), plan in reversed(
        list(zip(matches, plans))
    ):
        if cross is None:
            source_text = line[col:end]
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
            line_regions.append(
                (col, end, name, is_func, spliced, None, None, line_no)
            )
            continue
        # 跨行调用：本行余下文本 + 中间行 + 尾行前缀全部由该调用消费
        spliced = _splice_body(body, ctx.syntax)
        parts[col:] = [spliced]
        last_line = int(cross["last_line"])
        for k in range(line_no + 1, last_line):
            ctx.lines[k - 1] = ""
        ctx.lines[last_line - 1] = cross["last_after"]
        # 尾行掩码左移（截掉被吞前缀）：否则字符串/注释掩码偏移会误判尾行
        line_masks[last_line - 1] = _shift_masks(
            line_masks[last_line - 1], int(cross["close_col"]) + 1
        )
        line_regions.append(
            (col, len(line), name, is_func, spliced, cross["call_text"],
             int(cross["close_col"]), last_line)
        )
    ctx.lines[line_no - 1] = "".join(parts)
    ctx.restoration_stack.extend(reversed(forward_entries))
    if line_regions:
        entries: list[dict] = []
        delta = 0
        for s_col, s_end, name, is_func, body, src_override, close_col, end_line in sorted(
            line_regions, key=lambda r: r[0]
        ):
            cross = src_override is not None
            entries.append(
                {
                    "name": name,
                    "source_text": src_override if cross else line[s_col:s_end],
                    "is_func": is_func,
                    "body": body,
                    "src_line": line_no,
                    "src_col": s_col,
                    # 跨行：`src_end_col` = 闭括号在**尾行**的列，`src_end_line` 给
                    # 出尾行号（同行条目恒等于 src_line）；消费方以 source_text 为准。
                    "src_end_col": close_col if cross else s_end,
                    "src_end_line": end_line,
                    "in_line_col": s_col + delta,
                    "in_line_len": len(body),
                }
            )
            if not cross:  # 跨行是行内最后一个匹配，其长度增量不影响后续列
                delta += len(body) - (s_end - s_col)
        ctx.regions_by_line[line_no] = entries


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
                "src_end_line": line_no,
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


def map_invocations_to_source(
    invocations: list[dict],
    clean_to_raw: list,
    raw_source: str,
    macro_events: list[dict] | None,
) -> None:
    """调用点事实：clean 行 → **原始源行** + 宏时间线过滤（就地去留）。

    三步（顺序即去留判据）：
      1. 行映射不可用（`clean_to_raw` 为 None = include 拼接内容行，属别的文件
         坐标系）⇒ 丢弃；
      2. 原始行是**行拼接段首**（行尾仍有 continuation 字符）⇒ 该行由多条物理行
         合并，调用点列/行不可靠 ⇒ 丢弃（守卫式边界：不报位置错误的诊断）；
      3. 有事件表时按 `preprocessor.macro_timeline` 取该行时点的可见形参表：
         当时不是函数宏（后置定义 / `#undef` 后 / 对象宏）⇒ 丢弃；是则覆写
         `params`（**顺序语义**修正：展开器用最终宏表）。
    `macro_events` 为 None/空 ⇒ 第 3 步跳过（保留展开期快照）。
    """
    if not invocations:
        return
    raw_lines = raw_source.split("\n")
    cont = continuation_character()
    kept: list[dict] = []
    for inv in invocations:
        line = int(inv.get("line") or 0)
        raw = (
            clean_to_raw[line - 1]
            if 1 <= line <= len(clean_to_raw)
            else None
        )
        if raw is None:
            continue
        raw = int(raw)
        if cont and 1 <= raw <= len(raw_lines):
            if raw_lines[raw - 1].rstrip().endswith(cont):
                continue  # 行拼接段首：位置不可靠
        if macro_events:
            visible = macro_timeline.params_at(
                macro_events, raw, str(inv.get("name") or "")
            )
            if visible is None:
                continue  # 该时点不是函数宏
            inv["params"] = list(visible)
        inv["line"] = raw
        kept.append(inv)
    invocations[:] = kept
