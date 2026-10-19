"""include — `<前缀><关键字> <路径>` 指令处理器

指令**拼写**（前缀 + 关键字）由语言包 `[macro_recognition]` 形态声明提供，本模块
不写死——Verilog 是 `` `include ``，C 系是 `#include`，同一处理器覆盖。
路径**形态**（开/闭定界符 + 解析策略）由 `[directive_handlers.include] path_forms`
声明；未声明时回落到 C 系共同约定的引擎默认（见 `_DEFAULT_PATH_FORMS`）。
含递归展开和循环检测。
Doc: preprocessor/README.md
"""

import os

from core.errors import ConfigError

from .registry import register, split_directive

_DEFAULT_PATH_FORMS: tuple[dict, ...] = (
    {"open": '"', "close": '"', "relative_first": True},
    {"open": "<", "close": ">", "relative_first": False},
)
"""路径形态默认（引擎占位）：`"..."` 先相对当前文件目录、`<...>` 仅搜 search_dirs。

语言包可在 `[directive_handlers.include] path_forms` 显式声明覆盖——声明序即优先序，
每项 = `{ open, close, relative_first }`。
"""


# ── include 路径解析 ─────────────────────────────


def _path_forms(cfg: dict) -> list[dict]:
    """路径形态表（语言包声明优先；未声明 → 引擎默认）。

    形态非法（非列表 / 元素非表 / 缺非空 `open`·`close`）→ fail-fast（ADR-0003）。
    """
    raw = cfg.get("path_forms")
    if raw is None:
        return list(_DEFAULT_PATH_FORMS)
    if not isinstance(raw, list) or not raw:
        raise ConfigError("[directive_handlers.include] path_forms 须为非空列表")
    forms: list[dict] = []
    for i, item in enumerate(raw):
        open_ = item.get("open") if isinstance(item, dict) else None
        close = item.get("close") if isinstance(item, dict) else None
        if not isinstance(open_, str) or not isinstance(close, str) or not open_ or not close:
            raise ConfigError(
                f"[directive_handlers.include] path_forms[{i}] 须为表且含非空 open/close"
            )
        forms.append(
            {
                "open": open_,
                "close": close,
                "relative_first": bool(item.get("relative_first", False)),
            }
        )
    return forms


def _parse_target(arg: str, forms: list[dict]) -> tuple[str, dict] | None:
    """指令参数 → `(路径, 命中的形态)`；任一形态都不成立 → None。

    取**首个**闭定界符（同旧正则 `[^\"]+` / `[^>]+` 的语义）：行尾注释等多余文本
    不影响解析；形态声明序即优先序。
    """
    arg = arg.strip()
    for form in forms:
        open_, close = form["open"], form["close"]
        if arg.startswith(open_):
            end = arg.find(close, len(open_))
            if end > len(open_):
                return arg[len(open_) : end], form
    return None


def resolve_source_dir(source_path: str | None, rules_dir: str) -> str:
    """返回源文件所在目录，用于相对路径 include 解析。"""
    if source_path and os.path.isfile(source_path):
        return os.path.dirname(os.path.abspath(source_path))
    return os.path.abspath(rules_dir)


def _resolve_path(
    raw_path: str, base_dir: str, search_dirs: list[str], relative_first: bool = True
) -> str | None:
    """解析 include 文件路径。

    relative_first：先按当前文件目录解析，未命中再按 search_dirs；
    否则仅按 search_dirs（系统路径风格）。两个策略都由形态声明的 `relative_first`
    给出（引擎不假定哪种定界符对应哪种策略）。
    """
    if relative_first:
        candidate = os.path.join(base_dir, raw_path)
        if os.path.isfile(candidate):
            return os.path.normpath(candidate)
    for d in search_dirs:
        candidate = os.path.join(d, raw_path)
        if os.path.isfile(candidate):
            return os.path.normpath(candidate)
    return None


# ── include 问题处置（按语言包策略；引擎只执行策略） ──


def _report_problem(ctx: dict, kind: str, message: str) -> None:
    """缺失/循环/深度超限的处置。

    `on_missing = "warn"`（默认，verilog 不声明 ⇒ 行为与既有逐字一致）⇒ 打印；
    `"error"`（C 包声明）⇒ 不打印，记结构化诊断 `ctx["_include_diags"]`，由管线
    转成 `preprocessor_errors` / 受控 `error`。**不抛异常**（tpc 惯例：输入问题给
    诊断，非异常）。
    """
    cfg = ctx.get("_include_config", {})
    if cfg.get("on_missing") == "error":
        ctx.setdefault("_include_diags", []).append(
            {"kind": kind, "message": message}
        )
        return
    print(f"⚠️ [preprocessor] {message}")


@register("include")
def handle_include(stripped: str, prefix: str, _name: str, ctx: dict) -> None:
    """处理包含指令（路径形态由声明给出，关键字拼写不写死）。

    关键字拼写由调用方按语言包声明传入（见模块头）；参数从 `stripped` 按同一份
    切分规则取（与 `undef` / `define` 同源）。
    """
    del _name  # DirectiveHandler 协议签名参数（分派已用同一拼写判定过关键字）
    cfg = ctx.get("_include_config", {})
    parsed = _parse_target(split_directive(stripped, prefix)[1], _path_forms(cfg))
    if parsed is None:
        return
    raw_path, form = parsed

    inc_path = _resolve_path(
        raw_path, ctx["source_dir"], ctx["inc_dirs"], form["relative_first"]
    )
    if inc_path is None:
        if cfg.get("silent", False):
            return
        _report_problem(ctx, "missing", f"include 文件未找到: {raw_path}")
        return

    norm = os.path.normcase(inc_path)
    if norm in ctx["_include_stack"]:
        _report_problem(ctx, "cycle", f"循环 include 检测: {inc_path}，跳过")
        return

    max_depth = cfg.get("max_depth")
    if max_depth is not None and len(ctx["_include_stack"]) >= int(max_depth):
        _report_problem(
            ctx,
            "depth",
            f"include 递归深度超限（max_depth={max_depth}）: {inc_path}，跳过",
        )
        return

    ctx["_include_stack"].add(norm)
    try:
        with open(inc_path, encoding="utf-8") as f:
            inc_source = f.read()
        from .._expand import scan_directives

        child_diags: list[dict] = []
        (
            inc_macros,
            inc_funcs,
            inc_blocks,
            inc_placeholders,
            inc_dirs_raw,
            inc_clean,
            _,  # 被包含文件的行映射不并入宿主（拼接行不可映射，见下）
        ) = scan_directives(
            inc_source,
            ctx["rules_dir"],
            source_path=inc_path,
            _include_stack=ctx["_include_stack"],
            search_dirs=ctx["inc_dirs"],
            # marker 序号与宿主**共用**（嵌套各从 0 起会撞号 ⇒ restore 错位）
            seq_box=ctx["_seq_box"],
            out_diags=child_diags,
        )
        if child_diags:
            # 子扫描的诊断并入宿主（否则嵌套里的循环/深度诊断随子 ctx 丢失）
            ctx.setdefault("_include_diags", []).extend(child_diags)
        ctx["macro_defs"].update(inc_macros)
        ctx.setdefault("_func_params", {}).update(inc_funcs)
        # 定义事件快照：被包含文件里的定义行属**另一坐标系**（子扫描事件不向上
        # 传播），故按"include 行处、子文件最终状态"并入宿主时间线——本行之后
        # 的宿主调用点即可见（与 C 的 include 语义一致）。`params=None` = 非函数宏。
        include_line = int(ctx.get("_cur_raw_line") or ctx.get("_cur_line_no") or 0)
        events = ctx.setdefault("_macro_events", [])
        for name in inc_macros:
            events.append(
                {
                    "line": include_line,
                    "name": name,
                    "params": list(inc_funcs[name]) if name in inc_funcs else None,
                }
            )
        ctx.setdefault("_cond_blocks", []).extend(inc_blocks)
        ctx.setdefault("_cond_placeholders", {}).update(inc_placeholders)
        ctx["directive_lines"].extend(inc_dirs_raw)
        # 拼接行不属于宿主文件：行号账本记 None（映射时保守回退原行号）。
        # 归属与顺序必须和本指令的 marker 一致（条件分支内归分支；且排在
        # marker 之后——marker 由 `_handle_directive` 在调本 handler 前写入）。
        from .._expand import _emit_output_line

        stack = ctx.get("_ifdef_stack", [])
        for s in inc_clean.split("\n"):
            _emit_output_line(ctx, stack, None, s)
    finally:
        ctx["_include_stack"].discard(norm)
