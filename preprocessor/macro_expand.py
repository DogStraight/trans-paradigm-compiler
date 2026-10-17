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

from .macro_shape import MacroCallArgs

#: 展开次数预算的默认值（与 `[expand] max_iterations` 同义，仅作资源上限）
DEFAULT_BUDGET = 128


@dataclass(frozen=True)
class _Tok:
    """展开单元：文本 + hideset（不可变，构造后不再改）。"""

    text: str
    hide: frozenset[str] = frozenset()


def tokenize(text: str) -> list[_Tok]:
    """文本 → token 列表（标识符整段；非标识符逐字符——只为判 `NAME(` 边界）。

    逐字符切分不改变"拼接回去等于原文"（`join` 是逆运算）；宏调用实参的括号配平
    只依赖单字符定界符（语言包当前声明的 `(`/`)`/`,` 均单字符）。
    """
    toks: list[_Tok] = []
    i = 0
    while i < len(text):
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
    return bool(IDENT_RE.fullmatch(tok.text))


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
        if not prefixed or name in tok.hide or name not in macro_defs:
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
            )
            hide = tok.hide | {name}
            repl = [replace(t, hide=t.hide | hide) for t in tokenize(body)]
            _drop_prefix_token(out, prefix)
            work = repl + work[after:]
            i = 0
            continue
        steps += 1
        if steps > budget:
            out.extend(work[i:])
            break
        hide = tok.hide | {name}
        repl = [replace(t, hide=t.hide | hide) for t in tokenize(macro_defs[name])]
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
) -> str:
    """宏体替参（A1 子步：具名形参；实参**先展开**再替换）。

    `#`/`##`/`__VA_ARGS__` 在下一子步补：那时本函数需要给"紧邻 `#`/`##` 的形参"
    走**不展开**路径（标准语义），因此这里先保持"实参全展开"的简单形态。
    """
    body_toks = tokenize(body)
    out: list[_Tok] = []
    for t in body_toks:
        if _is_ident(t) and t.text in params:
            idx = params.index(t.text)
            arg_toks = args[idx] if idx < len(args) else []
            expanded = _expand_one(
                arg_toks, macro_defs, func_macros, call_args, budget, prefix
            )
            out.extend(replace(a, hide=a.hide | t.hide) for a in expanded)
            continue
        out.append(t)
    return join(out)


def expand_text(
    text: str,
    macro_defs: dict[str, str],
    func_macros: dict[str, list[str]],
    call_args: MacroCallArgs | None = None,
    *,
    prefix: str = "",
    budget: int = DEFAULT_BUDGET,
) -> str:
    """文本级展开入口（宏体/片段通用）：hideset 重扫描，超预算保留原文。

    `prefix` 缺省 `""` = 裸标识符调用；verilog 等前缀语言传声明的前缀文本
    （只有"前缀 + 名字"才是调用，裸出现同名标识符不展开）。
    """
    return join(
        _expand_one(tokenize(text), macro_defs, func_macros, call_args, budget, prefix)
    )
