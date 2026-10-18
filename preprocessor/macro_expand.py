"""macro_expand.py — 宏展开核心（hideset 重扫描）。

**为什么有它**：`_expand.py` 原用"宏体不动点文本替换"（逐轮 `re.sub` + 直接自引用
预判 + 体积截断）近似展开，自引用/互递归靠启发式，且"体保留未展开"是**静默近似**。
本模块按标准算法（token 携带 hideset，重扫描消解）实现：

- 每个 token 记 `hide`（"来自哪些宏"）：展开某宏时把该宏名并进替换 token 的 hide，
  重扫描时 hide 里已有的宏**不再展开** ⇒ 自引用/互递归抑制由算法保证
  （`#define x x` → `x`；`y→z→y` → `z`），不靠预判；
- `budget` 只是**资源上限守卫**（同一算法上的预算，不是第二套算法）：超限即停止
  继续展开（保留原文），调用方可用 `[expand] max_iterations` 配置。

语言无关：标识符形态取 `core.token_protocol.IDENT_RE`，实参括号/分隔符取语言包声明
的 `MacroCallArgs`（`[macro_recognition]` 的 `call_args` / `arg_separator`）。

覆盖：对象宏 + 函数宏（具名/变参形参）+ hideset 重扫描 + `#`（字符串化）/
`##`（粘贴）/ `__VA_ARGS__`；外加**实参空判**（`arg_tokens_blank`：注释在翻译阶段
已换成空白，供调用点事实的"单槽是否空"用，见 `preprocessor/README.md`）。

Doc: preprocessor/README.md
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.errors import ConfigError
from core.token_protocol import IDENT_RE

from .macro_shape import MacroCallArgs, MacroOperators

#: 展开次数预算的默认值（与 `[expand] max_iterations` 同义，仅作资源上限）
DEFAULT_BUDGET = 128


@dataclass(frozen=True)
class _Tok:
    """展开单元：文本 + hideset（不可变，构造后不再改）。

    `masked`：来自字符串/字符字面量或注释的整段文本——**永不参与宏匹配**
    （掩码与裸匹配在同一次扫描内生效）。
    """

    text: str
    hide: frozenset[str] = frozenset()
    masked: bool = False


def mask_spans(
    text: str,
    string_delimiters: tuple[str, ...] = (),
    escape: str | None = None,
    syntax=None,
) -> list[tuple[int, int]]:
    """掩码区间：字符串 / 字符字面量 / 行注释 / 块注释（左闭右开，按起点排序）。

    定界符与转义**只从语言包声明取**（token 表 `[string]` + `[comment]` 的
    `CommentSyntax`）；未声明 ⇒ 对应掩码不启用（不猜语言字符）。
    """
    spans: list[tuple[int, int]] = []
    delimiters = [d for d in string_delimiters if d]
    block_pairs = list(getattr(syntax, "block_pairs", ()) or ())
    line_starts = list(getattr(syntax, "line_starts", ()) or ())
    i = 0
    n = len(text)
    while i < n:
        line_hit = next((m for m in line_starts if text.startswith(m, i)), None)
        if line_hit is not None:
            end = text.find("\n", i)
            end = n if end < 0 else end
            spans.append((i, end))
            i = end
            continue
        block = next((p for p in block_pairs if text.startswith(p[0], i)), None)
        if block is not None:
            close = text.find(block[1], i + len(block[0]))
            end = n if close < 0 else close + len(block[1])
            spans.append((i, end))
            i = end
            continue
        delim = next((d for d in delimiters if text.startswith(d, i)), None)
        if delim is not None:
            j = i + len(delim)
            while j < n:
                if escape and text.startswith(escape, j):
                    j += len(escape) + 1
                    continue
                if text.startswith(delim, j):
                    j += len(delim)
                    break
                j += 1
            spans.append((i, j))
            i = j
            continue
        i += 1
    return spans


def tokenize(
    text: str,
    operators: MacroOperators | None = None,
    masks: list[tuple[int, int]] | None = None,
) -> list[_Tok]:
    """文本 → token 列表（标识符整段；语言声明的宏算子整段；其余逐字符）。

    逐字符切分不改变"拼接回去等于原文"（`join` 是逆运算）；宏调用实参的括号配平
    只依赖单字符定界符（语言包当前声明的 `(`/`)`/`,` 均单字符）。
    `operators` 声明的 `##` 等**多字符算子**必须先整体成 token，否则会被拆成两个
    `#` 而失去粘贴语义（`##` 是标准算子，由语言包声明、引擎不硬编码）。
    `masks`（来自 `mask_spans`）的整段区间作为**单个 masked token**——永不参与宏匹配。
    """
    toks: list[_Tok] = []
    i = 0
    mask_start = dict(masks or [])
    op_texts = (
        [op for op in (operators.paste, operators.stringize) if op]
        if operators is not None
        else []
    )
    op_texts.sort(key=len, reverse=True)  # 长串优先（`##` 不被 `#` 抢先切走）
    while i < len(text):
        if i in mask_start:
            end = mask_start[i]
            toks.append(_Tok(text[i:end], masked=True))
            i = end
            continue
        op = next((o for o in op_texts if text.startswith(o, i)), None)
        if op is not None:
            toks.append(_Tok(op))
            i += len(op)
            continue
        m = IDENT_RE.match(text, i)
        if m:
            toks.append(_Tok(m.group(0)))
            i = m.end()
            continue
        toks.append(_Tok(text[i]))
        i += 1
    return toks


def join(toks: list[_Tok]) -> str:
    """token 列表 → 原文本（与 `tokenize` 互逆）。"""
    return "".join(t.text for t in toks)


def _is_ident(tok: _Tok) -> bool:
    """标识符判定（**masked token 永不算标识符**——掩码与匹配同一次扫描生效）。"""
    return not tok.masked and bool(IDENT_RE.fullmatch(tok.text))


def _skip_blank_or_comment(toks: list[_Tok], j: int, syntax: Any) -> int:
    """`j` 起跳过**空白或注释** token（名字与 `(` 之间允许空白/注释，C99 §6.10.3）。

    注释在翻译阶段 3 已换成空白（GCC 16.1.0 实测 `f /*c*/ (2)` 正常展开），
    `_collect_args`/`_find_open` 的前导跳过必须把 masked 注释 token 当空白；
    只跳注释（`_is_comment_text` 判定），字符串/字符字面量掩码仍是 token。
    """
    while j < len(toks) and (
        not toks[j].text.strip()
        or (toks[j].masked and _is_comment_text(toks[j].text, syntax))
    ):
        j += 1
    return j


def _collect_args(
    toks: list[_Tok], start: int, call_args: MacroCallArgs, syntax: Any = None
) -> tuple[list[list[_Tok]] | None, int]:
    """从 `start`（名字之后）收集实参 → (实参 token 列表, 闭括号后下标)。

    形如 `( a , b(c) )`：跳过名字与 `(` 间空白/注释；顶层分隔符切分；括号对配平计深。
    非调用形态（没有开括号 / 未配平）→ (None, start)（调用方按非调用处理）。
    """
    j = _skip_blank_or_comment(toks, start, syntax)
    if j >= len(toks) or toks[j].text != call_args.open:
        return None, start
    openers = {o for o, _ in call_args.nesting}
    closers = {c for _, c in call_args.nesting}
    depth = 0
    args: list[list[_Tok]] = []
    cur: list[_Tok] = []
    j += 1
    while j < len(toks):
        t = toks[j]
        if t.text in openers:
            depth += 1
            cur.append(t)
            j += 1
            continue
        if t.text in closers:
            if depth == 0:
                args.append(cur)
                return _trim_args(args), j + 1
            depth -= 1
            cur.append(t)
            j += 1
            continue
        if depth == 0 and t.text == call_args.separator:
            args.append(cur)
            cur = []
            j += 1
            continue
        cur.append(t)
        j += 1
    return None, start


def _trim_args(args: list[list[_Tok]]) -> list[list[_Tok]]:
    """实参**首尾空白 token** 不属实参（token 级收集会保留它们）。

    与文本级 `split(..., strip)` 语义对齐；内部空白保留（字符串化需要）。
    """
    trimmed: list[list[_Tok]] = []
    for arg in args:
        a, b = 0, len(arg)
        while a < b and not arg[a].text.strip():
            a += 1
        while b > a and not arg[b - 1].text.strip():
            b -= 1
        trimmed.append(arg[a:b])
    return trimmed


def arg_tokens_blank(arg: list[_Tok], syntax: Any = None) -> bool:
    """单个实参的 token 列表是否**不含任何预处理 token**（只含空白/注释）。

    C99+TC §6.10.3p18「The sequence of preprocessing tokens bounded by the
    outside-most matching parentheses forms the list of arguments」：注释在
    翻译阶段 3 已换成空白、不是预处理 token ⇒ `#define Z() 1` + `Z(/*c*/)`
    与 `Z()` 等价（GCC 16.1 实测接受）。故判"空实参"必须把注释算空。

    注释形态来自语言包 `[comment]` 声明（`CommentSyntax`），引擎不写死
    `//`/`/* */`。`syntax=None` ⇒ 只按空白判（调用方无语境）。
    """
    for tok in arg:
        if not tok.text.strip():
            continue
        if tok.masked and _is_comment_text(tok.text, syntax):
            continue
        return False
    return True


def _is_comment_text(text: str, syntax: Any) -> bool:
    """掩码文本是否整段是一条注释（行注释起始标记 / 成对块注释整体）。"""
    if syntax is None:
        return False
    line_starts = tuple(getattr(syntax, "line_starts", ()) or ())
    if any(text.startswith(mark) for mark in line_starts):
        return True
    raw_pairs: Any = getattr(syntax, "block_pairs", ())
    if not raw_pairs:
        return False
    for open_mark, close_mark in raw_pairs:
        if text.startswith(open_mark) and text.endswith(close_mark):
            return True
    return False


def _tokenize_masked(
    text: str, operators: MacroOperators | None, syntax
) -> list[_Tok]:
    """按声明算掩码后 tokenize（**宏体内部**的字面量/注释同样不参与匹配）。

    掩码与匹配必须同一次扫描生效：不仅源文本要掩码，**替换进流的宏体**也要
    （`#define A 1` + `#define B "A"` ⇒ 展开 `B` 得 `"A"`，不是 `"1"`）。
    """
    ops = operators
    masks = mask_spans(
        text,
        ops.string_delimiters if ops else (),
        ops.escape if ops else None,
        syntax,
    )
    return tokenize(text, ops, masks)


def _find_open(
    toks: list[_Tok], start: int, call_args: MacroCallArgs, syntax: Any = None
) -> int | None:
    """名字之后（跳空白/注释）的开括号 token 下标；非调用形态 → None（同 `_collect_args`）。"""
    j = _skip_blank_or_comment(toks, start, syntax)
    if j < len(toks) and toks[j].text == call_args.open:
        return j
    return None


def _variadic_raw(
    toks: list[_Tok], open_idx: int, named_count: int, call_args: MacroCallArgs
) -> str:
    """开括号之后**变参区原文拼写**（首个具名实参之后、闭括号之前，含区间内逗号与空白）。

    `#__VA_ARGS__` 的字符串化口径 = **实参列表原文**（GCC 16.1 实测 `V(a, b)` →
    `"a, b"`、`V(a ,  b)` → `"a , b"`、`V( a, b )` → `"a, b"`）；按 token 重拼会
    丢掉逗号后的空白 ⇒ 取原文切片，空白折叠交给 `_stringize`。
    """
    openers = {o for o, _ in call_args.nesting}
    closers = {c for _, c in call_args.nesting}
    depth = 0
    seps = 0
    buf: list[_Tok] = []
    for t in toks[open_idx + 1 :]:
        if t.text in openers:
            depth += 1
            buf.append(t)
            continue
        if t.text in closers:
            if depth == 0:
                break
            depth -= 1
            buf.append(t)
            continue
        if depth == 0 and t.text == call_args.separator:
            seps += 1
            if seps <= named_count:  # 该分隔符分隔具名区（或具名区与变参区）
                buf.clear()
            else:
                buf.append(t)
            continue
        buf.append(t)
    return join(buf).strip()


def _call_raw_variadic(
    toks: list[_Tok],
    name_idx: int,
    after: int,
    name: str,
    call_args: MacroCallArgs,
    func_macros: dict[str, list[str]],
    operators: MacroOperators | None,
    macro_defs: dict[str, str],
    syntax: Any = None,
) -> str | None:
    """token 流里的调用 → 变参区原文拼写（`#__VA_ARGS__` 用）；不适用 → None。"""
    if operators is None or operators.variadic is None:
        return None
    if "..." not in func_macros.get(name, []):
        return None
    if not _body_mentions(macro_defs.get(name, ""), operators.variadic, operators):
        return None
    open_idx = _find_open(toks, name_idx + 1, call_args, syntax)
    if open_idx is None or after <= open_idx:
        return None
    named = [p for p in func_macros[name] if p != "..."]
    return _variadic_raw(toks, open_idx, len(named), call_args)


def variadic_raw_text(
    text: str,
    call_args: MacroCallArgs,
    named_count: int,
    operators: MacroOperators | None = None,
    syntax=None,
) -> str | None:
    """调用点文本（**名字之后**、含括号）→ 变参区原文拼写；非调用形态 → None。

    给文本层（`_expand.py::_match_one`）用：`#__VA_ARGS__` 必须取原文（P1-1）。
    """
    toks = _tokenize_masked(text, operators, syntax)
    open_idx = _find_open(toks, 0, call_args, syntax)
    if open_idx is None:
        return None
    return _variadic_raw(toks, open_idx, named_count, call_args)


def _expand_one(
    toks: list[_Tok],
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None,
    budget: int,
    prefix: str,
    operators: MacroOperators | None = None,
    syntax=None,
) -> list[_Tok]:
    """对 `toks` 做重扫描展开（原地循环；替换文本插回当前位置重扫）。

    `prefix` = 调用前缀文本（语言包声明）：非空时只有"**紧随前缀**的标识符"才是
    调用（前缀随调用一起被吃掉——与文本层既有语义一致）；`""` = 裸标识符调用
    （C 形态，显式声明才启用）。
    """
    work = list(toks)
    out: list[_Tok] = []
    i = 0
    steps = 0
    while i < len(work):
        tok = work[i]
        name = tok.text
        prefixed = prefix == "" or (
            i > 0 and work[i - 1].text == prefix and _is_ident(tok)
        )
        if tok.masked or not prefixed or name in tok.hide or name not in macro_defs:
            out.append(tok)
            i += 1
            continue
        if name in func_macros:
            if call_args is None:
                out.append(tok)
                i += 1
                continue
            args, after = _collect_args(work, i + 1, call_args, syntax)
            if args is None:
                out.append(tok)
                i += 1
                continue
            steps += 1
            if steps > budget:
                out.extend(work[i:])
                break
            raw_variadic = _call_raw_variadic(
                work, i, after, name, call_args, func_macros, operators, macro_defs,
                syntax,
            )
            body = _substitute(
                macro_defs.get(name, ""),
                func_macros[name],
                args,
                macro_defs,
                func_macros,
                call_args,
                budget - steps,
                prefix,
                operators,
                syntax,
                raw_variadic=raw_variadic,
            )
            hide = tok.hide | {name}
            repl = [
                replace(t, hide=t.hide | hide)
                for t in _tokenize_masked(body, operators, syntax)
            ]
            _drop_prefix_token(out, prefix)
            work = repl + work[after:]
            i = 0
            continue
        steps += 1
        if steps > budget:
            out.extend(work[i:])
            break
        hide = tok.hide | {name}
        repl = [
            replace(t, hide=t.hide | hide)
            for t in _tokenize_masked(macro_defs[name], operators, syntax)
        ]
        _drop_prefix_token(out, prefix)
        work = repl + work[i + 1 :]
        i = 0
    return out


def _drop_prefix_token(out: list[_Tok], prefix: str) -> None:
    """调用被展开 ⇒ 前缀 token 一并消费（已追加进 `out` 时把它弹出）。"""
    if prefix and out and out[-1].text == prefix:
        out.pop()


def _body_mentions(body: str, name: str, operators: MacroOperators | None) -> bool:
    """宏体里是否出现某标识符（变参名误用检查用；按算子切分后的 token 判）。"""
    return any(t.text == name for t in tokenize(body, operators))


def _substitute(
    body: str,
    params: list[str],
    args: list[list[_Tok]],
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None,
    budget: int,
    prefix: str,
    operators: MacroOperators | None = None,
    syntax=None,
    raw_variadic: str | None = None,
) -> str:
    """宏体替参 + `#`（字符串化）/ `##`（粘贴）/ `__VA_ARGS__`。

    标准语义要点（C99 §6.10.3.2–§6.10.3.4）：
    - **`#` 形参**：取实参的**未展开拼写**再字符串化（`S(hi there)` → `"hi there"`）；
    - **`#__VA_ARGS__`**：取**实参列表原文**（`V(a, b)` → `"a, b"`；逗号后的空白
      保留，再由 `_stringize` 折叠）——按 token 重拼会丢空白 ⇒ 用 `raw_variadic`；
    - **紧邻 `##` 的形参**：用**未展开拼写**粘贴（`CAT(EMPTY,x)` → `EMPTYx`，**不是**
      先展开成 `x`——`##` 用未展开拼写是"宏算法是否合规"的试金石）；
    - 其余形参：实参**先展开**再替换；
    - **变参**（`operators.variadic` 声明时才启用）：替换为"超出具名形参的实参"
      按 `,` 连接；为空 ⇒ 空串（标准行为：宏体里的逗号**保留**——`F(1)` → `f(1, )`；
      GNU `, ## __VA_ARGS__` 的删逗号是扩展，本引擎不实现）。
    `operators` 未声明对应算子 ⇒ 该语义**不启用**（普通替换）。
    """
    ops = operators or MacroOperators()
    variadic_name = ops.variadic
    # 形参记录里 `...` 是**变参标记**（`define.py` 保留）：真形参 = 去掉标记后的项；
    # 非变参宏里出现 `__VA_ARGS__`/`#__VA_ARGS__` ⇒ 明确报错（不猜"超出即变参"）
    is_variadic = "..." in params
    params = [p for p in params if p != "..."]
    has_var_args = (
        variadic_name is not None and _body_mentions(body, variadic_name, ops)
    )
    if has_var_args and not is_variadic:
        raise ConfigError(
            f"非变参宏的宏体使用了 {variadic_name!r}：形参表需含 '...'（宏体：{body!r}）"
        )
    toks = _tokenize_masked(body, ops, syntax)
    variadic = args[len(params):]
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        # `#`：字符串化（`#` 与随后的形参/变参之间**允许空白**；取未展开拼写）
        if ops.stringize is not None and t.text == ops.stringize:
            j = _skip_space(toks, i + 1)
            if j < len(toks) and _is_ident(toks[j]) and toks[j].text in params:
                raw = _raw_spelling(toks[j].text, params, args)
                out.append(_Tok(_stringize(raw, ops, syntax), t.hide))
                i = j + 1
                continue
            if (
                variadic_name is not None
                and j < len(toks)
                and _is_ident(toks[j])
                and toks[j].text == variadic_name
            ):
                sep = call_args.separator if call_args is not None else ""
                raw = (
                    raw_variadic
                    if raw_variadic is not None
                    else sep.join(join(a) for a in variadic)
                )
                out.append(_Tok(_stringize(raw, ops, syntax), t.hide))
                i = j + 1
                continue
        if _is_ident(t) and t.text in params:
            idx = params.index(t.text)
            arg_toks = args[idx] if idx < len(args) else []
            if _adjacent_paste(toks, i, ops.paste):
                # 紧邻 `##`：未展开拼写（粘贴在 `_apply_paste` 统一做）
                out.extend(replace(a, hide=a.hide | t.hide) for a in arg_toks)
            else:
                expanded = _expand_one(
                    arg_toks, macro_defs, func_macros, call_args, budget, prefix, ops,
                    syntax,
                )
                out.extend(replace(a, hide=a.hide | t.hide) for a in expanded)
            i += 1
            continue
        if variadic_name is not None and _is_ident(t) and t.text == variadic_name:
            # 变参：超出具名形参的实参按**声明的实参分隔符**连接（未展开拼写）。
            # `call_args` 为 None 时本分支不可达：函数宏展开入口
            # （`_expand_one` 的 `name in func_macros` 分支）要求 `call_args` 非 None。
            sep = call_args.separator if call_args is not None else ""
            if variadic:
                for k, arg_toks in enumerate(variadic):
                    if k:
                        out.append(_Tok(sep))
                    out.extend(replace(a, hide=a.hide | t.hide) for a in arg_toks)
            i += 1
            continue
        out.append(t)
        i += 1
    return join(_apply_paste(out, ops.paste))


def _raw_spelling(param: str, params: list[str], args: list[list[_Tok]]) -> str:
    """形参 → 实参的**未展开拼写**（`#` 字符串化与 `##` 粘贴共用）。"""
    idx = params.index(param)
    if idx >= len(args):
        return ""
    return join(args[idx])


def _skip_space(toks: list[_Tok], i: int) -> int:
    """`i` 起跳过纯空白 token（`##`/`#` 两侧允许空白；空 token 也跳过）。"""
    while i < len(toks) and not toks[i].text.strip():
        i += 1
    return i


def _adjacent_paste(toks: list[_Tok], i: int, paste: str | None) -> bool:
    """`i` 处的形参是否**隔着空白**紧邻粘贴算子（左或右）——决定是否跳过展开。"""
    if paste is None:
        return False
    j = i - 1
    while j >= 0 and not toks[j].text.strip():
        j -= 1
    left = j >= 0 and toks[j].text == paste
    k = _skip_space(toks, i + 1)
    right = k < len(toks) and toks[k].text == paste
    return left or right


def _comment_spans(raw: str, syntax) -> list[tuple[int, int]]:
    """注释区间（行注释/块注释；来自语言包 `[comment]` 声明）——字符串化前换成空格。"""
    spans: list[tuple[int, int]] = []
    if syntax is None:
        return spans
    line_starts = list(getattr(syntax, "line_starts", ()) or ())
    block_pairs = list(getattr(syntax, "block_pairs", ()) or ())
    i = 0
    n = len(raw)
    while i < n:
        line_hit = next((m for m in line_starts if raw.startswith(m, i)), None)
        if line_hit is not None:
            end = raw.find("\n", i)
            end = n if end < 0 else end
            spans.append((i, end))
            i = end
            continue
        block = next((p for p in block_pairs if raw.startswith(p[0], i)), None)
        if block is not None:
            close = raw.find(block[1], i + len(block[0]))
            end = n if close < 0 else close + len(block[1])
            spans.append((i, end))
            i = end
            continue
        i += 1
    return spans


def _stringize(
    raw: str, operators: MacroOperators | None, syntax=None
) -> str:
    """实参拼写 → 字符串字面量（C99 §6.10.3.2p2）。

    规则：**预处理 token 之间**的空白折叠为**一个空格**；token **内部**（字符串/
    字符字面量内部的连续空白）**不得动**；首尾空白丢弃；**注释**按翻译阶段换成
    一个空格（`S(a /* c */ b)` → `"a b"`）。故不能 `re.sub(r"\\s+")` 一把梭——
    按 token 判：定界段整体算一个 token，其余逐字符，只在源里有空白间隔处补空格。
    """
    ops = operators or MacroOperators()
    # 注释 → 空格（翻译阶段 3：注释替换为单个空格）
    for a, b in reversed(_comment_spans(raw, syntax)):
        raw = raw[:a] + " " + raw[b:]
    pieces: list[tuple[str, bool]] = []  # (token 文本, 之前是否有空白)
    i = 0
    had_space = False
    delimiters = ops.string_delimiters
    escape = ops.escape
    while i < len(raw):
        ch = raw[i]
        if ch.isspace():
            had_space = True
            i += 1
            continue
        delim = next((d for d in delimiters if raw.startswith(d, i)), None)
        if delim is not None:
            j = i + len(delim)
            while j < len(raw):
                if escape and raw.startswith(escape, j):
                    j += len(escape) + 1
                    continue
                if raw.startswith(delim, j):
                    j += len(delim)
                    break
                j += 1
            pieces.append((raw[i:j], had_space))
            had_space = False
            i = j
            continue
        m = IDENT_RE.match(raw, i)
        if m:
            pieces.append((m.group(0), had_space))
            had_space = False
            i = m.end()
            continue
        pieces.append((ch, had_space))
        had_space = False
        i += 1
    joined = "".join(
        ((" " if ws and k else "") + text) for k, (text, ws) in enumerate(pieces)
    )
    escaped = joined.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _apply_paste(toks: list[_Tok], paste: str | None) -> list[_Tok]:
    """执行粘贴：`lhs <paste> rhs` → 一个 token（空操作数走占位符规则）。

    `paste` 未声明（None）⇒ 不启用粘贴语义（算子 token 原样保留）。
    结果按**新 token** 处理（文本拼接；标识符/数字形态的下游重扫描再判宏表）。
    """
    if paste is None:
        return toks
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.text == paste:
            # `##` 两侧允许空白：先剥掉左/右侧空白 token，再拼成一个 token
            while out and not out[-1].text.strip():
                out.pop()
            lhs = out.pop() if out else _Tok("")
            j = _skip_space(toks, i + 1)
            rhs = toks[j] if j < len(toks) else _Tok("")
            pasted = f"{lhs.text}{rhs.text}"
            hide = lhs.hide | rhs.hide
            out.append(_Tok(pasted, hide) if pasted else _Tok(""))
            i = j + 1
            continue
        out.append(t)
        i += 1
    return out


def collect_args_tokens(
    text: str,
    call_args: MacroCallArgs,
    operators: MacroOperators | None = None,
    syntax=None,
) -> tuple[list[list[_Tok]], int] | None:
    """从 `text` 起点收实参（**token 级**，复用 `_collect_args` 单一实现）。

    返回 (实参 token 列表, 消耗的**字符数**)；无调用（无开括号/未配平）→ None。
    掩码在 tokenize 时生效 ⇒ 字符串/注释里的 `,`/`)` 不会误当分隔符/收束符
    （P0-B；调用点不再走文本级 `MacroCallArgs.match_args/split`）。
    """
    toks = _tokenize_masked(text, operators, syntax)
    args, after = _collect_args(toks, 0, call_args, syntax)
    if args is None:
        return None
    return args, sum(len(t.text) for t in toks[:after])


def substitute_call_tokens(
    name: str,
    args: list[list[_Tok]],
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None,
    *,
    operators: MacroOperators | None = None,
    syntax=None,
    budget: int = DEFAULT_BUDGET,
    raw_args: str | None = None,
) -> str:
    """调用点替参（**token 级实参**）→ hideset 重扫描；与体展开同一套语义。

    `raw_args` = 调用**实参列表原文**（名字之后到闭括号，含括号）里变参区的
    原文切片，供 `#__VA_ARGS__` 用（`V(a, b)` → `"a, b"` 的逗号后空白不丢）。
    """
    return join(
        substitute_call_tokens_tokens(
            name,
            args,
            macro_defs,
            func_macros,
            call_args,
            operators=operators,
            syntax=syntax,
            budget=budget,
            raw_args=raw_args,
        )
    )


def substitute_call_tokens_tokens(
    name: str,
    args: list[list[_Tok]],
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None,
    *,
    operators: MacroOperators | None = None,
    syntax=None,
    budget: int = DEFAULT_BUDGET,
    raw_args: str | None = None,
    hideset: frozenset[str] = frozenset(),
    prefix: str = "",
) -> list[_Tok]:
    """`substitute_call_tokens` 的 **token 返回**版本（接缝重扫用：保留 hideset）。

    `hideset` = 调用区间的 hideset **交集**（Prosser：替换文本 hide = 交集 ∪
    {宏名}）；缺省 ∅ ⇒ 与文本层原口径 `{name}` 一致。`prefix` = 调用前缀文本
    （替换文本/实参内部再展开用；C 为 `""`，verilog 为声明前缀）。
    """
    body = macro_defs.get(name)
    if body is None:
        return []
    text = _substitute(
        body,
        func_macros.get(name, []),
        args,
        macro_defs,
        func_macros,
        call_args,
        budget,
        prefix,
        operators,
        syntax,
        raw_variadic=raw_args,
    )
    hide = hideset | {name}
    toks = [
        replace(t, hide=t.hide | hide)
        for t in _tokenize_masked(text, operators, syntax)
    ]
    return _expand_one(
        toks, macro_defs, func_macros, call_args, budget, prefix, operators, syntax
    )


def expand_text(
    text: str,
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None = None,
    *,
    prefix: str = "",
    budget: int = DEFAULT_BUDGET,
    operators: MacroOperators | None = None,
    syntax=None,
    hideset: frozenset[str] = frozenset(),
) -> str:
    """文本级展开入口（宏体/片段通用）：hideset 重扫描，超预算保留原文。

    `prefix` 缺省 `""` = 裸标识符调用；verilog 等前缀语言传声明的前缀文本
    （只有"前缀 + 名字"才是调用，裸出现同名标识符不展开）。
    `operators` 未声明 ⇒ `#`/`##`/变参语义不启用（纯替换）。
    `syntax`（`CommentSyntax`）+ `operators.string_delimiters/escape` ⇒ 掩码：
    字符串/字符/行注释/块注释内的文本**不参与**宏匹配（同一次扫描内生效）。
    `hideset` = **初始 hideset**（种子）：调用点替换传 `{name}` 防自递归
    ——公开 API，调用方/测试不必碰私有函数。
    """
    return join(
        expand_text_tokens(
            text,
            macro_defs,
            func_macros,
            call_args,
            prefix=prefix,
            budget=budget,
            operators=operators,
            syntax=syntax,
            hideset=hideset,
        )
    )


def expand_text_tokens(
    text: str,
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None = None,
    *,
    prefix: str = "",
    budget: int = DEFAULT_BUDGET,
    operators: MacroOperators | None = None,
    syntax=None,
    hideset: frozenset[str] = frozenset(),
) -> list[_Tok]:
    """`expand_text` 的 **token 返回**版本（接缝重扫用：保留各 token 的 hideset）。

    语义与参数同 `expand_text`（同一实现，无第二套）；差别只在返回值 = token 列表，
    供文本层在"替换文本 + 源码后续"的接缝处继续重扫。
    """
    ops = operators
    masks = (
        mask_spans(
            text,
            ops.string_delimiters if ops else (),
            ops.escape if ops else None,
            syntax,
        )
        if ops is not None or syntax is not None
        else None
    )
    toks = tokenize(text, ops, masks)
    if hideset:
        toks = [replace(t, hide=t.hide | hideset) for t in toks]
    return _expand_one(
        toks, macro_defs, func_macros, call_args, budget, prefix, ops, syntax,
    )


def collect_args_at(
    toks: list[_Tok], start: int, call_args: MacroCallArgs, syntax: Any = None
) -> tuple[list[list[_Tok]], int] | None:
    """从 token 流 `start` 处收实参（接缝重扫用；与 `_collect_args` 同一实现）。

    非调用形态（无开括号/未配平）→ None（与 `collect_args_tokens` 同口径）。
    """
    args, after = _collect_args(toks, start, call_args, syntax)
    if args is None:
        return None
    return args, after
