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

范围（首片 A1 子步）：对象宏 + 函数宏（具名形参）+ 重扫描/自引用抑制。
`#`（字符串化）/`##`（粘贴）/`__VA_ARGS__` 是下一子步（本模块先把调用/替参骨架
立起来，届时在 `_substitute` 内补三处语义）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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


def _collect_args(
    toks: list[_Tok], start: int, call_args: MacroCallArgs
) -> tuple[list[list[_Tok]] | None, int]:
    """从 `start`（名字之后）收集实参 → (实参 token 列表, 闭括号后下标)。

    形如 `( a , b(c) )`：跳过名字与 `(` 间空白；顶层分隔符切分；括号对配平计深。
    非调用形态（没有开括号 / 未配平）→ (None, start)（调用方按非调用处理）。
    """
    j = start
    while j < len(toks) and not _is_ident(toks[j]) and not toks[j].text.strip():
        j += 1
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
                return args, j + 1
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


def _expand_one(
    toks: list[_Tok],
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None,
    budget: int,
    prefix: str,
    operators: MacroOperators | None = None,
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
            args, after = _collect_args(work, i + 1, call_args)
            if args is None:
                out.append(tok)
                i += 1
                continue
            steps += 1
            if steps > budget:
                out.extend(work[i:])
                break
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
            )
            hide = tok.hide | {name}
            repl = [replace(t, hide=t.hide | hide) for t in tokenize(body, operators)]
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
            for t in tokenize(macro_defs[name], operators)
        ]
        _drop_prefix_token(out, prefix)
        work = repl + work[i + 1 :]
        i = 0
    return out


def _drop_prefix_token(out: list[_Tok], prefix: str) -> None:
    """调用被展开 ⇒ 前缀 token 一并消费（已追加进 `out` 时把它弹出）。"""
    if prefix and out and out[-1].text == prefix:
        out.pop()


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
) -> str:
    """宏体替参 + `#`（字符串化）/ `##`（粘贴）/ `__VA_ARGS__`。

    标准语义要点（C99 §6.10.3.2–§6.10.3.4）：
    - **`#` 形参**：取实参的**未展开拼写**再字符串化（`S(hi there)` → `"hi there"`）；
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
    toks = tokenize(body, ops)
    variadic = args[len(params):]
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        # `#形参`：字符串化（未展开拼写）；仅当语言声明了字符串化算子
        if (
            ops.stringize is not None
            and t.text == ops.stringize
            and i + 1 < len(toks)
            and _is_ident(toks[i + 1])
            and toks[i + 1].text in params
        ):
            raw = _raw_spelling(toks[i + 1].text, params, args)
            out.append(_Tok(_stringize(raw, operators), t.hide))
            i += 2
            continue
        if _is_ident(t) and t.text in params:
            idx = params.index(t.text)
            arg_toks = args[idx] if idx < len(args) else []
            if _adjacent_paste(toks, i, ops.paste):
                # 紧邻 `##`：未展开拼写（粘贴在 `_apply_paste` 统一做）
                out.extend(replace(a, hide=a.hide | t.hide) for a in arg_toks)
            else:
                expanded = _expand_one(
                    arg_toks, macro_defs, func_macros, call_args, budget, prefix, ops
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


def _adjacent_paste(toks: list[_Tok], i: int, paste: str | None) -> bool:
    """`i` 处的形参是否紧邻粘贴算子（左或右）——决定是否跳过实参展开。"""
    if paste is None:
        return False
    left = i - 1 >= 0 and toks[i - 1].text == paste
    right = i + 1 < len(toks) and toks[i + 1].text == paste
    return left or right


def _stringize(raw: str, operators: MacroOperators | None) -> str:
    """实参拼写 → 字符串字面量（C99 §6.10.3.2p2）。

    规则：**预处理 token 之间**的空白折叠为**一个空格**；token **内部**（字符串/
    字符字面量内部的连续空白）**不得动**；首尾空白丢弃。故不能 `re.sub(r"\\s+")`
    一把梭（会把 `S("a  b")` 的内部空白也压掉）——按 token 判：
      · 语言声明了 `[string] delimiters`/`escape` ⇒ 定界段整体算一个 token；
      · 标识符整段；其余字符逐字符（punctuation）；
      · 只在**源里有空白间隔**的两个 token 之间补一个空格。
    """
    ops = operators or MacroOperators()
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
            lhs = out.pop() if out else _Tok("")
            rhs = toks[i + 1] if i + 1 < len(toks) else _Tok("")
            pasted = f"{lhs.text}{rhs.text}"
            hide = lhs.hide | rhs.hide
            out.append(_Tok(pasted, hide) if pasted else _Tok(""))
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def substitute_call(
    name: str,
    args_text: str,
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None,
    *,
    operators: MacroOperators | None = None,
    syntax=None,
    budget: int = DEFAULT_BUDGET,
) -> str:
    """**调用点**带参宏展开：实参切分 → 替参（`#`/`##`/变参）→ hideset 重扫描。

    与 `expand_text` 共用同一套语义（`_substitute`）；调用点只多做"按语言声明的
    分隔符切实参"这一步。替换结果 token 带 `{name}` hideset（自递归抑制）。
    """
    body = macro_defs.get(name)
    if body is None:
        return ""
    if call_args is None:
        return body
    params = func_macros.get(name, [])
    ops = operators
    args: list[list[_Tok]] = []
    for arg_text in call_args.split(args_text):
        masks = mask_spans(
            arg_text,
            ops.string_delimiters if ops else (),
            ops.escape if ops else None,
            syntax,
        )
        args.append(tokenize(arg_text, ops, masks))
    text = _substitute(
        body, params, args, macro_defs, func_macros, call_args, budget, "", ops
    )
    masks = mask_spans(
        text,
        ops.string_delimiters if ops else (),
        ops.escape if ops else None,
        syntax,
    )
    hide = frozenset({name})
    toks = [replace(t, hide=t.hide | hide) for t in tokenize(text, ops, masks)]
    return join(_expand_one(toks, macro_defs, func_macros, call_args, budget, "", ops))


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
) -> str:
    """文本级展开入口（宏体/片段通用）：hideset 重扫描，超预算保留原文。

    `prefix` 缺省 `""` = 裸标识符调用；verilog 等前缀语言传声明的前缀文本
    （只有"前缀 + 名字"才是调用，裸出现同名标识符不展开）。
    `operators` 未声明 ⇒ `#`/`##`/变参语义不启用（纯替换）。
    `syntax`（`CommentSyntax`）+ `operators.string_delimiters/escape` ⇒ 掩码：
    字符串/字符/行注释/块注释内的文本**不参与**宏匹配（同一次扫描内生效）。
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
    return join(
        _expand_one(
            tokenize(text, ops, masks), macro_defs, func_macros, call_args, budget,
            prefix, ops,
        )
    )
