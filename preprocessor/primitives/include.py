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
        silent = cfg.get("silent", False)
        if not silent:
            print(f"⚠️ [preprocessor] include 文件未找到: {raw_path}")
        return

    norm = os.path.normcase(inc_path)
    if norm in ctx["_include_stack"]:
        print(f"⚠️ [preprocessor] 循环 include 检测: {inc_path}，跳过")
        return

    ctx["_include_stack"].add(norm)
    try:
        with open(inc_path, encoding="utf-8") as f:
            inc_source = f.read()
        from .._expand import scan_directives

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
        )
        ctx["macro_defs"].update(inc_macros)
        ctx.setdefault("_func_params", {}).update(inc_funcs)
        ctx.setdefault("_cond_blocks", []).extend(inc_blocks)
        ctx.setdefault("_cond_placeholders", {}).update(inc_placeholders)
        ctx["directive_lines"].extend(inc_dirs_raw)
        # 拼接行不属于宿主文件：行号账本记 None（映射时保守回退原行号）
        ctx["_inject_lines"].extend((None, s) for s in inc_clean.split("\n"))
    finally:
        ctx["_include_stack"].discard(norm)
