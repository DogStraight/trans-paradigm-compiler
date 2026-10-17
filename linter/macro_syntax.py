"""宏定义的**形式化语法**检查（linter 阶段，AST 前）。

作者定调（2026-10-17）：形式化语法错误走 linter（AST 前），语义级走 check 插件族。
宏定义行在扫指令时被消费、不进 lint 流 ⇒ 其**语法**约束必须在这里对原始源码检查。

语言知识全来自声明面（引擎不硬编码 C）：
- 指令前缀/关键字：`[macro_recognition]` 形态声明（与 `scan_directives` 同源）
- 形参表形态：`call_args`（开/闭/分隔符）
- 宏算子：`#` / `##` / 变参名（`[macro_recognition]` 声明）
- 定义侧形式语法：`[macro_syntax]` 段（如 `variadic_marker`）——**语言包声明本段才启用**；
  verilog 未声明 ⇒ 不跑，避免把 C 的定义语法套到别的语言上（Verilog 侧补齐是触发式项，
  见 `docs/decisions/0021-long-term-deferral-strategy.md`）。

只报**形式化**约束（GCC 同样报 error 的形态）：
① 宏名缺失/非法；② 形参表：空项、非标识符、变参占位非末位或重复、重名；
③ 宏体：`#` 后非形参/非变参名、`##` 在首/尾。
**语义级**（实参个数校验等，需要宏表与调用点上下文）→ check 插件族（后续项）。
Doc: linter/linter_architecture.md
"""

from core.token_protocol import IDENT_RE
from lexer.comment_syntax import load_comment_syntax
from preprocessor._expand import directive_handlers
from preprocessor.macro_expand import mask_spans, tokenize
from preprocessor.macro_shape import (
    MacroSyntax,
    load_macro_call_args,
    load_macro_operators,
    load_macro_syntax,
)

from . import LintDiagnostic, Position


def macro_syntax_diagnostics(source: str, rules_dir: str) -> list[LintDiagnostic]:
    """宏定义的语法约束诊断（linter 阶段；语言包未声明 `[macro_syntax]` ⇒ 空）。"""
    syntax_decl = load_macro_syntax(rules_dir=rules_dir)
    if syntax_decl is None:
        return []
    define_keywords = {
        kw
        for kw, cfg in directive_handlers().items()
        if isinstance(cfg, dict)
        and cfg.get("op", kw) == "define"
        and cfg.get("enabled", True)
    }
    if not define_keywords:
        return []
    from preprocessor._expand import _load_config

    prefix, _ = _load_config(rules_dir)
    call_args = load_macro_call_args(rules_dir=rules_dir)
    operators = load_macro_operators(rules_dir=rules_dir)
    comment = load_comment_syntax(rules_dir)
    out: list[LintDiagnostic] = []
    for line_no, line in enumerate(source.split("\n"), 1):
        out.extend(
            _check_define_line(
                line,
                line_no,
                prefix,
                define_keywords,
                call_args,
                operators,
                comment,
                syntax_decl,
            )
        )
    return out


def _diag(line_no: int, col: int, width: int, message: str, code: str) -> LintDiagnostic:
    return LintDiagnostic(
        range=(
            Position(line_no - 1, col),
            Position(line_no - 1, col + max(width, 1)),
        ),
        code=code,
        message=message,
    )


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t":
        i += 1
    return i


def _check_define_line(
    line: str,
    line_no: int,
    prefix: str,
    define_keywords: set[str],
    call_args,
    operators,
    syntax,
    syntax_decl: MacroSyntax,
) -> list[LintDiagnostic]:
    """单行 `#define` 语法检查（非 define 指令行 → 空）。"""
    diags: list[LintDiagnostic] = []
    i = len(line) - len(line.lstrip())
    if not prefix or not line.startswith(prefix, i):
        return diags
    j = i + len(prefix)
    m = IDENT_RE.match(line, j)
    if m is None or m.group(0) not in define_keywords:
        return diags
    keyword = m.group(0)
    j = _skip_ws(line, m.end())
    name = IDENT_RE.match(line, j)
    if name is None:
        diags.append(
            _diag(
                line_no,
                j,
                1,
                f"宏名缺失或非法：`{prefix}{keyword}` 后需要标识符",
                "macro-name",
            )
        )
        return diags
    k = name.end()
    params: list[str] = []
    variadic_marker = syntax_decl.variadic_marker
    if call_args is not None and line.startswith(call_args.open, k):
        open_col = k
        close = line.find(call_args.close, k + len(call_args.open))
        if close < 0:
            diags.append(
                _diag(
                    line_no,
                    open_col,
                    1,
                    f"形参表未闭合：缺少 '{call_args.close}'",
                    "macro-param",
                )
            )
            return diags
        raw = line[k + len(call_args.open) : close]
        params, param_diags = _check_params(
            raw,
            open_col + len(call_args.open),
            line_no,
            call_args,
            variadic_marker,
        )
        diags.extend(param_diags)
        k = close + len(call_args.close)
    body = line[k:]
    diags.extend(_check_body(body, k, line_no, params, operators, syntax))
    return diags


def _split_params(raw: str, sep: str) -> list[tuple[str, int]]:
    """按声明分隔符切分形参表 → `[(原文段, 段在 raw 内的起点)]`（不剥空白）。"""
    if not sep:
        return [(raw, 0)]
    parts: list[tuple[str, int]] = []
    start = 0
    while True:
        pos = raw.find(sep, start)
        if pos < 0:
            parts.append((raw[start:], start))
            return parts
        parts.append((raw[start:pos], start))
        start = pos + len(sep)


def _check_params(
    raw: str,
    base_col: int,
    line_no: int,
    call_args,
    variadic_marker: str | None,
) -> tuple[list[str], list[LintDiagnostic]]:
    """形参表：空项 / 非标识符 / 变参占位位置与重复 / 重名。"""
    diags: list[LintDiagnostic] = []
    if not raw.strip():
        return [], diags  # `F()` 合法（空形参表）
    items = _split_params(raw, call_args.separator)
    params: list[str] = []
    seen: dict[str, int] = {}
    for idx, (item, offset) in enumerate(items):
        text = item.strip()
        start = base_col + offset + (len(item) - len(item.lstrip()))
        if not text:
            diags.append(
                _diag(line_no, start, 1, "形参表含空项（多余的分隔符）", "macro-param")
            )
            continue
        if variadic_marker is not None and text == variadic_marker:
            if idx != len(items) - 1:
                diags.append(
                    _diag(
                        line_no,
                        start,
                        len(text),
                        f"'{variadic_marker}' 只能出现在形参表末尾",
                        "macro-param",
                    )
                )
        elif IDENT_RE.fullmatch(text):
            if text in seen:
                diags.append(
                    _diag(line_no, start, len(text), f"形参重名：'{text}'", "macro-param")
                )
            seen[text] = start
            params.append(text)
        else:
            allowed = (
                f"标识符或 '{variadic_marker}'"
                if variadic_marker is not None
                else "标识符"
            )
            diags.append(
                _diag(
                    line_no,
                    start,
                    len(text),
                    f"形参须为{allowed}：'{text}'",
                    "macro-param",
                )
            )
    return params, diags


def _check_body(
    body: str,
    base_col: int,
    line_no: int,
    params: list[str],
    operators,
    syntax,
) -> list[LintDiagnostic]:
    """宏体：`#` 后须为形参/变参名；`##` 不得在首/尾。"""
    diags: list[LintDiagnostic] = []
    stringize, paste = operators.stringize, operators.paste
    if stringize is None and paste is None:
        return diags
    toks = tokenize(
        body,
        operators,
        mask_spans(
            body,
            operators.string_delimiters,
            operators.escape,
            syntax,
        ),
    )
    cols: list[int] = []
    pos = 0
    for t in toks:
        cols.append(pos)
        pos += len(t.text)
    ident = [i for i, t in enumerate(toks) if t.text.strip()]
    if not ident:
        return diags
    if paste is not None and toks[ident[0]].text == paste:
        diags.append(
            _diag(
                line_no,
                base_col + cols[ident[0]],
                len(paste),
                f"'{paste}' 不能出现在宏体首部",
                "macro-body",
            )
        )
    if paste is not None and toks[ident[-1]].text == paste:
        diags.append(
            _diag(
                line_no,
                base_col + cols[ident[-1]],
                len(paste),
                f"'{paste}' 不能出现在宏体末尾",
                "macro-body",
            )
        )
    if stringize is not None:
        for idx in ident:
            if toks[idx].text != stringize:
                continue
            nxt = next((k for k in ident if k > idx), None)
            ok = nxt is not None and (
                toks[nxt].text in params
                or (operators.variadic is not None and toks[nxt].text == operators.variadic)
            )
            if not ok:
                diags.append(
                    _diag(
                        line_no,
                        base_col + cols[idx],
                        len(stringize),
                        f"'{stringize}' 后须为形参名或变参名",
                        "macro-body",
                    )
                )
    return diags
