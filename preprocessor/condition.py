"""condition.py — `#if` / `#elif` 整型常量表达式求值（语言包声明驱动）。

作者裁定（`docs/gaps/gap-c-preprocessor-scope.md` ⑥，2026-10-17）：`#if` 的求值语义
放**语言包声明面**，引擎不持有 C 知识。本模块只实现**通用求值器**，声明面
`[condition]`（`grammar/c/base/_macro.toml`）提供：

- 算子：符号 → 引擎动作（动作词表见 `_ACTIONS`）+ 结合性；声明序 = 优先级（低→高）；
  三目项的 `second` = 第二分隔符；一元项写 `position = "prefix"`；
- 整型常量：形态（正则 + 基数 + 无后缀溢出规则）与后缀（正则 + 无符号字符）；
- 整型模型：`intmax_bits`（C99 §6.10.1p4：signed/unsigned 分别按 intmax_t/uintmax_t）；
- 字符常量：定界符 + 转义表 + 数值转义；
- 分组记号与 `defined` 拼写。

未声明 `[condition]` ⇒ `load_condition_syntax` 返回 None（该语言不接线表达式求值；
verilog 的 `ifdef`/`elsif` 宏名语义保持原样）。

求值顺序（C99 §6.10.1）：① 先求 `defined`（操作数**不**宏展开）→ ② 宏展开其余 →
③ 剩余标识符换 0 → ④ 整型常量表达式求值（`&&`/`||`/`?:` 短路；有符号溢出 / 除零 /
非法常量 / 语法错误 → 结构化诊断，不抛异常）。

Doc: preprocessor/README.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.errors import ConfigError
from core.token_protocol import IDENT_RE

from .macro_expand import MacroCallArgs, expand_text, mask_spans
from .macro_shape import MacroOperators, _resolve_macro_cfg, load_macro_operators, load_macro_shapes

CONDITION_KEY = "condition"

# ── 引擎动作词表（语言包声明「符号 → 动作」；动作的语义在引擎） ──
# 值 = 元数。动作名是引擎机制面（与 renderer/primitives 的键同类），不是语言知识。
_ACTIONS: dict[str, int] = {
    "logical-or": 2,
    "logical-and": 2,
    "bitwise-or": 2,
    "bitwise-xor": 2,
    "bitwise-and": 2,
    "equal": 2,
    "not-equal": 2,
    "less": 2,
    "greater": 2,
    "less-equal": 2,
    "greater-equal": 2,
    "shift-left": 2,
    "shift-right": 2,
    "add": 2,
    "subtract": 2,
    "multiply": 2,
    "divide": 2,
    "modulo": 2,
    "conditional": 3,
    "unary-plus": 1,
    "unary-minus": 1,
    "logical-not": 1,
    "bitwise-not": 1,
}
_COMPARE_ACTIONS = frozenset(
    {
        "logical-or",
        "logical-and",
        "equal",
        "not-equal",
        "less",
        "greater",
        "less-equal",
        "greater-equal",
    }
)
_SHIFT_ACTIONS = frozenset({"shift-left", "shift-right"})
_POSITION_INFIX = "infix"
_POSITION_PREFIX = "prefix"
# 内部 token / 表达式节点类别名（**刻意不与任何语言关键字字面量同名**——硬编码门禁 R1
# 规则把"引擎代码里出现 grammar 关键字字面量"视为语言知识泄漏；这两个只是内部类别）。
_K_INT = "int-literal"
_K_CHAR = "char-literal"


# ── 声明解析结果 ──────────────────────────────────────


@dataclass(frozen=True)
class OperatorDef:
    """一个算子声明（符号 → 动作；优先级 = 声明序，结合性随项）。"""

    symbol: str
    action: str
    assoc: str
    arity: int
    position: str
    precedence: int
    second: str | None = None


@dataclass(frozen=True)
class IntegerForm:
    """整型常量形态（正则 + 基数 + 无后缀溢出是否按无符号）。"""

    pattern: re.Pattern[str]
    base: int
    no_suffix_unsigned: bool


@dataclass(frozen=True)
class CharacterSyntax:
    """字符常量形态（C99 §6.4.4.4；转义表/数值转义由声明给出）。"""

    delimiter: str
    escape: str
    prefixes: tuple[str, ...]
    simple_escape: dict[str, int]
    octal: bool
    hex_prefix: str | None
    multi_character: str | None
    char_bits: int
    char_signed: bool
    prefix_bits: dict[str, int]


@dataclass(frozen=True)
class ConditionSyntax:
    """`[condition]` 声明解析结果（求值器全部知识来源）。"""

    defined: str
    lparen: str
    rparen: str
    infix: tuple[OperatorDef, ...]
    prefix: tuple[OperatorDef, ...]
    symbols: tuple[str, ...]
    integers: tuple[IntegerForm, ...]
    suffix_pattern: re.Pattern[str]
    unsigned_chars: frozenset[str]
    intmax_bits: int
    character: CharacterSyntax

    @property
    def mask(self) -> int:
        """无符号模型位掩码（uintmax_t 的宽度取 `intmax_bits`）。"""
        return (1 << self.intmax_bits) - 1

    @property
    def int_max(self) -> int:
        return (1 << (self.intmax_bits - 1)) - 1

    @property
    def int_min(self) -> int:
        return -(1 << (self.intmax_bits - 1))

    def infix_by_symbol(self, symbol: str) -> OperatorDef | None:
        for op in self.infix:
            if op.symbol == symbol:
                return op
        return None

    def prefix_by_symbol(self, symbol: str) -> OperatorDef | None:
        for op in self.prefix:
            if op.symbol == symbol:
                return op
        return None


def load_condition_syntax(rules_dir: str) -> ConditionSyntax | None:
    """读取 `[condition]` 声明：未声明 → None（不接线）；非法 → ConfigError。"""
    cfg = _resolve_macro_cfg(rules_dir)
    raw = cfg.get(CONDITION_KEY)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError(f"[{CONDITION_KEY}] 须是表（得到 {type(raw).__name__}）")
    return _parse_syntax(raw)


def _parse_syntax(raw: dict[str, Any]) -> ConditionSyntax:
    defined = _req_text(raw, "defined")
    lparen = _req_text(raw, "lparen")
    rparen = _req_text(raw, "rparen")
    if lparen == rparen:
        raise ConfigError("[condition] lparen / rparen 须为不同文本")
    bits = raw.get("intmax_bits")
    if not isinstance(bits, int) or not 8 <= bits <= 64:
        raise ConfigError(
            f"[condition] intmax_bits 须为 8–64 的整数（得到 {bits!r}）"
        )
    infix, prefix = _parse_operators(raw)
    symbols = {op.symbol for op in (*infix, *prefix)}
    symbols.update(op.second for op in infix if op.second is not None)
    integers = _parse_integers(raw)
    suffix_raw = raw.get("suffix_pattern")
    if not isinstance(suffix_raw, str) or not suffix_raw:
        raise ConfigError(
            f"[condition] suffix_pattern 须为非空正则字符串（得到 {suffix_raw!r}）"
        )
    try:
        suffix_pattern = re.compile(suffix_raw)
    except re.error as exc:
        raise ConfigError(f"[condition] suffix_pattern 非法: {suffix_raw!r}（{exc}）") from exc
    if not suffix_pattern.match(""):
        raise ConfigError(
            f"[condition] suffix_pattern 须能匹配空串（无后缀合法），得到 {suffix_raw!r}"
        )
    unsigned_chars = raw.get("unsigned_chars")
    if not isinstance(unsigned_chars, str) or not unsigned_chars:
        raise ConfigError(
            f"[condition] unsigned_chars 须为非空字符串（得到 {unsigned_chars!r}）"
        )
    character = _parse_character(raw)
    return ConditionSyntax(
        defined=defined,
        lparen=lparen,
        rparen=rparen,
        infix=infix,
        prefix=prefix,
        symbols=tuple(sorted(symbols, key=len, reverse=True)),
        integers=integers,
        suffix_pattern=suffix_pattern,
        unsigned_chars=frozenset(unsigned_chars),
        intmax_bits=bits,
        character=character,
    )


def _req_text(raw: dict[str, Any], key: str) -> str:
    """`[condition]` 必填的非空字符串键（非法 → fail-fast）。"""
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"[condition] {key} 须为非空字符串（得到 {value!r}）")
    return value


def _parse_operators(
    raw: dict[str, Any],
) -> tuple[tuple[OperatorDef, ...], tuple[OperatorDef, ...]]:
    """算子声明 → (中缀/三目, 一元)；中缀序 = 优先级（低→高）。"""
    infix = _operator_list(raw, "operator", _POSITION_INFIX)
    prefix = _operator_list(raw, "unary", _POSITION_PREFIX)
    return infix, prefix


def _operator_list(
    raw: dict[str, Any], key: str, position: str
) -> tuple[OperatorDef, ...]:
    items = raw.get(key) or []
    if not isinstance(items, list) or not items:
        raise ConfigError(f"[condition] {key} 须为非空算子声明列表")
    out: list[OperatorDef] = []
    seen: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(f"[condition] {key}[{idx}] 须是表")
        symbol = item.get("symbol")
        action = item.get("action")
        if not isinstance(symbol, str) or not symbol:
            raise ConfigError(f"[condition] {key}[{idx}].symbol 须为非空字符串")
        if symbol in seen:
            raise ConfigError(f"[condition] {key} 符号 {symbol!r} 重复声明")
        seen.add(symbol)
        if not isinstance(action, str) or action not in _ACTIONS:
            raise ConfigError(
                f"[condition] {key}[{idx}].action 未知: {action!r}"
                f"（引擎动作词表: {', '.join(sorted(_ACTIONS))}）"
            )
        arity = _ACTIONS[action]
        if position == _POSITION_PREFIX and arity != 1:
            raise ConfigError(
                f"[condition] {key}[{idx}]: 一元项动作须为一元（得到 {action!r}）"
            )
        if position == _POSITION_INFIX and arity == 1:
            raise ConfigError(
                f"[condition] {key}[{idx}]: 中缀项动作不能是一元（得到 {action!r}）"
            )
        assoc = item.get("assoc", "left")
        if assoc not in ("left", "right"):
            raise ConfigError(
                f"[condition] {key}[{idx}].assoc 须为 'left' / 'right'（得到 {assoc!r}）"
            )
        second = item.get("second")
        if action == "conditional" and second is None:
            raise ConfigError(
                f"[condition] {key}[{idx}]: 三目项须声明 second（第二分隔符）"
            )
        if second is not None and (not isinstance(second, str) or not second):
            raise ConfigError(f"[condition] {key}[{idx}].second 须为非空字符串")
        out.append(
            OperatorDef(
                symbol=symbol,
                action=action,
                assoc=assoc,
                arity=arity,
                position=position,
                precedence=idx,
                second=second if isinstance(second, str) else None,
            )
        )
    if position == _POSITION_PREFIX:
        # 一元项一律高过任何中缀项（与 pratt 的 unary rbp 口径一致）
        out = [
            OperatorDef(
                symbol=op.symbol,
                action=op.action,
                assoc=op.assoc,
                arity=op.arity,
                position=op.position,
                precedence=len(raw.get("operator") or []),
                second=op.second,
            )
            for op in out
        ]
    return tuple(out)


def _parse_integers(raw: dict[str, Any]) -> tuple[IntegerForm, ...]:
    items = raw.get("int_literal") or []
    if not isinstance(items, list) or not items:
        raise ConfigError("[condition] int_literal 须为非空形态声明列表")
    out: list[IntegerForm] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(f"[condition] int_literal[{idx}] 须是表")
        pattern = item.get("pattern")
        base = item.get("base")
        if not isinstance(pattern, str) or not pattern:
            raise ConfigError(f"[condition] int_literal[{idx}].pattern 须为非空正则字符串")
        if not isinstance(base, int) or base < 2:
            raise ConfigError(f"[condition] int_literal[{idx}].base 须为 ≥2 的整数")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ConfigError(
                f"[condition] int_literal[{idx}].pattern 非法: {pattern!r}（{exc}）"
            ) from exc
        out.append(
            IntegerForm(
                pattern=compiled,
                base=base,
                no_suffix_unsigned=bool(item.get("no_suffix_unsigned", False)),
            )
        )
    return tuple(out)


def _parse_character(raw: dict[str, Any]) -> CharacterSyntax:
    subs = raw.get("character")
    if not isinstance(subs, dict):
        raise ConfigError("[condition] character 须是表")
    delimiter = subs.get("delimiter")
    escape = subs.get("escape")
    if not isinstance(delimiter, str) or not delimiter:
        raise ConfigError("[condition.character] delimiter 须为非空字符串")
    if not isinstance(escape, str) or not escape:
        raise ConfigError("[condition.character] escape 须为非空字符串")
    prefixes_raw = subs.get("prefixes") or []
    if not isinstance(prefixes_raw, list) or not all(
        isinstance(p, str) and p for p in prefixes_raw
    ):
        raise ConfigError("[condition.character] prefixes 须为非空字符串列表")
    simple_raw = subs.get("simple_escape") or {}
    if not isinstance(simple_raw, dict):
        raise ConfigError("[condition.character] simple_escape 须是表")
    simple: dict[str, int] = {}
    for key, value in simple_raw.items():
        if not isinstance(value, int) or not isinstance(key, str):
            raise ConfigError(
                f"[condition.character] simple_escape[{key!r}] 须映射到整数（得到 {value!r}）"
            )
        simple[key] = value
    octal = subs.get("octal_escape", False)
    if not isinstance(octal, bool):
        raise ConfigError("[condition.character] octal_escape 须为布尔值")
    hex_prefix = subs.get("hex_escape_prefix")
    if hex_prefix is not None and (not isinstance(hex_prefix, str) or not hex_prefix):
        raise ConfigError("[condition.character] hex_escape_prefix 须为非空字符串或省略")
    multi = subs.get("multi_character")
    if multi is not None and multi != "gcc-shift-or":
        raise ConfigError(
            "[condition.character] multi_character 只支持 'gcc-shift-or'（或省略 = 不支持）"
        )
    char_bits = subs.get("char_bits", 8)
    if not isinstance(char_bits, int) or not 1 <= char_bits <= 64:
        raise ConfigError(
            f"[condition.character] char_bits 须为 1–64 的整数（得到 {char_bits!r}）"
        )
    char_signed = subs.get("char_signed", True)
    if not isinstance(char_signed, bool):
        raise ConfigError("[condition.character] char_signed 须为布尔值")
    prefix_bits_raw = subs.get("prefix_bits") or {}
    if not isinstance(prefix_bits_raw, dict):
        raise ConfigError("[condition.character] prefix_bits 须是表")
    prefix_bits: dict[str, int] = {}
    for prefix, width in prefix_bits_raw.items():
        if not isinstance(width, int) or not 1 <= width <= 64:
            raise ConfigError(
                f"[condition.character] prefix_bits[{prefix!r}] 须为 1–64 的整数"
            )
        prefix_bits[str(prefix)] = width
    for prefix in prefixes_raw:
        if prefix not in prefix_bits:
            raise ConfigError(
                f"[condition.character] 前缀 {prefix!r} 未声明宽度（prefix_bits）"
            )
    return CharacterSyntax(
        delimiter=delimiter,
        escape=escape,
        prefixes=tuple(sorted(prefixes_raw, key=len, reverse=True)),
        simple_escape=simple,
        octal=octal,
        hex_prefix=hex_prefix,
        multi_character=multi,
        char_bits=char_bits,
        char_signed=char_signed,
        prefix_bits=prefix_bits,
    )


# ── 求值环境（按 ctx 缓存：宏表 + 掩码/展开形态） ──────────


@dataclass
class _EvalEnv:
    operators: MacroOperators
    call_prefix: str
    macro_defs: dict[str, str]
    func_macros: dict[str, list[str]]
    call_args: MacroCallArgs | None
    budget: int
    comment: Any


def _eval_env(ctx: dict[str, Any]) -> _EvalEnv:
    """条件求值环境（按 ctx 缓存；形态全部按语言包解析）。"""
    env = ctx.get("_cond_env")
    if isinstance(env, _EvalEnv):
        return env
    rules_dir = ctx["rules_dir"]
    # 预定义（-D）宏也算宏表；-U 优先剔除；源码内 #define 覆盖 -D
    defs = dict(ctx.get("_predefined") or {})
    for name in ctx.get("_undefine") or ():
        defs.pop(name, None)
    defs.update(ctx.get("macro_defs") or {})
    operators = load_macro_operators(rules_dir=rules_dir)
    call = load_macro_shapes(rules_dir=rules_dir).get("call")
    if call is None:
        raise ConfigError(
            "[condition] 声明了条件表达式求值，但语言包未声明宏调用形态"
            "（[macro_recognition].call）——求值需要宏展开面"
        )
    from ._expand import _get_expand_config

    from lexer.comment_syntax import load_comment_syntax

    env = _EvalEnv(
        operators=operators,
        call_prefix=call.prefix,
        macro_defs=defs,
        func_macros=dict(ctx.get("_func_params") or {}),
        call_args=ctx.get("_call_args"),
        budget=int(_get_expand_config().get("max_iterations", 128)),
        comment=load_comment_syntax(rules_dir),
    )
    ctx["_cond_env"] = env
    return env


def _masks(text: str, env: _EvalEnv) -> list[tuple[int, int]]:
    return mask_spans(
        text,
        env.operators.string_delimiters,
        env.operators.escape,
        env.comment,
    )


def is_macro_defined(ctx: dict[str, Any], name: str) -> bool:
    """宏是否已定义（`-U` 优先，其次 `-D`，最后源码宏表）——条件指令共用的谓词。"""
    if name in (ctx.get("_undefine") or ()):
        return False
    if name in (ctx.get("_predefined") or {}):
        return True
    return name in (ctx.get("macro_defs") or {})


# ── 诊断 / 求值入口 ───────────────────────────────────


class _CondError(Exception):
    """表达式错误（位置 = 表达式文本内偏移；由入口转成结构化诊断）。"""

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.message = message
        self.pos = pos


def evaluate_condition(
    expr: str,
    ctx: dict[str, Any],
    syntax: ConditionSyntax,
    *,
    line: int,
    column_base: int,
) -> tuple[bool, list[dict[str, Any]]]:
    """`#if` / `#elif` 表达式求值 → (真值, 诊断列表)。

    诊断 `{kind: "condition", message, line, column}`（不抛异常；不写终端）。
    `column_base` = 表达式文本在源行内的 0-based 起点（诊断列 = base + 偏移 + 1）。
    """
    diags: list[dict[str, Any]] = []

    def report(message: str, pos: int) -> None:
        diags.append(
            {
                "kind": "condition",
                "message": message,
                "line": line,
                "column": column_base + pos + 1,
            }
        )

    try:
        value = _evaluate(expr, ctx, syntax)
    except _CondError as exc:
        report(exc.message, exc.pos)
        return False, diags
    return value != 0, diags


def _evaluate(expr: str, ctx: dict[str, Any], syntax: ConditionSyntax) -> int:
    """完整求值（C99 §6.10.1 顺序；错误抛 _CondError）。"""
    if not expr.strip():
        raise _CondError("条件表达式为空", 0)
    env = _eval_env(ctx)
    masks = _masks(expr, env)
    substituted, err = _substitute_defined(expr, masks, syntax, ctx)
    if err is not None:
        raise _CondError(*err)
    expanded = expand_text(
        substituted,
        env.macro_defs,
        env.func_macros,
        env.call_args,
        prefix=env.call_prefix,
        budget=env.budget,
        operators=env.operators,
        syntax=env.comment,
    )
    # 宏展开产生的 `defined`：C 标准未定义、gcc 逐字处理并告警（-Wexpansion-to-defined）
    expanded_masks = _masks(expanded, env)
    if _has_defined_token(expanded, expanded_masks, syntax):
        raise _CondError(
            "宏展开产生了 `defined`（C 标准未定义该用法；gcc: -Wexpansion-to-defined）",
            _first_defined_pos(expanded, expanded_masks, syntax),
        )
    toks, serr = _tokenize(expanded, syntax, env)
    if serr is not None:
        raise _CondError(*serr)
    toks = _replace_identifiers(toks)
    node = _Parser(toks, syntax).parse()
    return _eval_node(node, syntax)


def _substitute_defined(
    text: str,
    masks: list[tuple[int, int]],
    syntax: ConditionSyntax,
    ctx: dict[str, Any],
) -> tuple[str, tuple[str, int] | None]:
    """求 `defined`（操作数**不**宏展开）→ 替换成 1/0。返回 (文本, 错误)。"""
    out: list[str] = []
    i = 0
    mask_starts = dict(masks)
    n = len(text)
    while i < n:
        end = mask_starts.get(i)
        if end is not None:
            out.append(text[i:end])
            i = end
            continue
        m = IDENT_RE.match(text, i)
        if m is None:
            out.append(text[i])
            i += 1
            continue
        word = m.group(0)
        if word != syntax.defined:
            out.append(word)
            i = m.end()
            continue
        pos = i
        j = _skip_ws(text, m.end())
        paren = text.startswith(syntax.lparen, j)
        if paren:
            j = _skip_ws(text, j + len(syntax.lparen))
        operand = IDENT_RE.match(text, j)
        if operand is None:
            return text, (f"`{syntax.defined}` 后须为标识符或 ({syntax.lparen}标识符{syntax.rparen})", pos)
        j = operand.end()
        if paren:
            j = _skip_ws(text, j)
            if not text.startswith(syntax.rparen, j):
                return text, (f"`{syntax.defined}` 的括号未闭合", pos)
            j += len(syntax.rparen)
        out.append("1" if is_macro_defined(ctx, operand.group(0)) else "0")
        i = j
    return "".join(out), None


def _has_defined_token(
    text: str, masks: list[tuple[int, int]], syntax: ConditionSyntax
) -> bool:
    """展开后文本里是否还有 `defined` 标识符（掩码外）。"""
    return _first_defined_pos(text, masks, syntax) >= 0


def _first_defined_pos(
    text: str, masks: list[tuple[int, int]], syntax: ConditionSyntax
) -> int:
    mask_starts = dict(masks)
    i = 0
    n = len(text)
    while i < n:
        end = mask_starts.get(i)
        if end is not None:
            i = end
            continue
        m = IDENT_RE.match(text, i)
        if m is None:
            i += 1
            continue
        if m.group(0) == syntax.defined:
            return i
        i = m.end()
    return -1


# ── 词法（声明驱动：字面量形态 / 字符常量 / 算子 / 分组记号） ──


@dataclass(frozen=True)
class _Tok:
    kind: str  # int | char | ident | op | lparen | rparen
    text: str
    pos: int
    value: int = 0
    unsigned: bool = False


def _tokenize(
    text: str, syntax: ConditionSyntax, env: _EvalEnv
) -> tuple[list[_Tok], tuple[str, int] | None]:
    """表达式文本 → token 列表（错误返回 (消息, 偏移)）。"""
    masks = _masks(text, env)
    comment_starts: dict[int, int] = {}
    literal_starts: dict[int, int] = {}
    for start, end in masks:
        # 掩码区间按语义分派：注释 → 跳过；字符串/字符 → 逐类处理
        if _is_comment_at(text, start, env.comment):
            comment_starts[start] = end
        else:
            literal_starts[start] = end
    toks: list[_Tok] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r":
            i += 1
            continue
        char = _scan_char(text, i, syntax)
        if char is not None:
            tok, i = char
            toks.append(tok)
            continue
        end = comment_starts.get(i)
        if end is not None:
            i = end
            continue
        end = literal_starts.get(i)
        if end is not None:
            span = text[i:end]
            if span.startswith(syntax.character.delimiter) or any(
                span.startswith(p + syntax.character.delimiter)
                for p in syntax.character.prefixes
            ):
                return [], ("字符常量未闭合", i)
            return [], ("字符串常量不能出现在条件表达式中", i)
        if text.startswith(syntax.lparen, i):
            toks.append(_Tok("lparen", syntax.lparen, i))
            i += len(syntax.lparen)
            continue
        if text.startswith(syntax.rparen, i):
            toks.append(_Tok("rparen", syntax.rparen, i))
            i += len(syntax.rparen)
            continue
        op = next((s for s in syntax.symbols if text.startswith(s, i)), None)
        if op is not None:
            toks.append(_Tok("op", op, i))
            i += len(op)
            continue
        integer = _scan_integer(text, i, syntax)
        if integer is not None:
            tok, i = integer
            toks.append(tok)
            continue
        m = IDENT_RE.match(text, i)
        if m is not None:
            toks.append(_Tok("ident", m.group(0), i))
            i = m.end()
            continue
        return [], (f"无法识别的记号 {ch!r}", i)
    return toks, None


def _is_comment_at(text: str, i: int, comment: Any) -> bool:
    """掩码区间起点是注释（行注释起始 / 块注释开界符）。"""
    line_starts = getattr(comment, "line_starts", ()) or ()
    block_pairs = getattr(comment, "block_pairs", ()) or ()
    return any(text.startswith(m, i) for m in line_starts) or any(
        text.startswith(pair[0], i) for pair in block_pairs
    )


def _scan_integer(text: str, i: int, syntax: ConditionSyntax) -> tuple[_Tok, int] | None:
    """整型常量（声明形态 + 声明后缀；值模型 = intmax/uintmax）。"""
    best: tuple[int, IntegerForm] | None = None
    for form in syntax.integers:
        m = form.pattern.match(text, i)
        if m is None:
            continue
        if best is None or m.end() > best[0]:
            best = (m.end(), form)
    if best is None:
        return None
    end, form = best
    digits = text[i:end]
    m = syntax.suffix_pattern.match(text, end)
    suffix = m.group(0) if m is not None else ""
    end += len(suffix)
    has_unsigned_suffix = any(c in syntax.unsigned_chars for c in suffix)
    try:
        value = int(digits, form.base)
    except ValueError:
        return None
    unsigned = _constant_type(value, has_unsigned_suffix, form, syntax, i)
    return _Tok(_K_INT, text[i:end], i, value=value, unsigned=unsigned), end


def _constant_type(
    value: int, unsigned_suffix: bool, form: IntegerForm, syntax: ConditionSyntax, pos: int
) -> bool:
    """整型常量的符号性（gcc 预处理器口径：装得进 intmax 即有符号，否则无符号）。"""
    if unsigned_suffix:
        if value > syntax.mask:
            raise _CondError("整数常量超出 uintmax_t 范围", pos)
        return True
    if value <= syntax.int_max:
        return False
    if form.no_suffix_unsigned and value <= syntax.mask:
        return True
    raise _CondError("整数常量超出 intmax_t 范围", pos)


def _scan_char(text: str, i: int, syntax: ConditionSyntax) -> tuple[_Tok, int] | None:
    """字符常量（含声明前缀；转义见声明）。非法内容抛 _CondError。"""
    chr_ = syntax.character
    used: str | None = None
    j = i
    for prefix in chr_.prefixes:
        if text.startswith(prefix, i):
            used = prefix
            j = i + len(prefix)
            break
    if not text.startswith(chr_.delimiter, j):
        return None
    content_start = j + len(chr_.delimiter)
    values: list[int] = []
    k = content_start
    while k < len(text):
        if text.startswith(chr_.delimiter, k):
            value = _char_value(values, syntax, i, used)
            return _Tok(_K_CHAR, text[i : k + len(chr_.delimiter)], i, value=value), k + len(
                chr_.delimiter
            )
        if chr_.escape and text.startswith(chr_.escape, k):
            k, value = _escape_value(text, k, syntax, i)
            values.append(value)
            continue
        values.append(ord(text[k]))
        k += 1
    raise _CondError("字符常量未闭合", i)


def _escape_value(
    text: str, k: int, syntax: ConditionSyntax, base_pos: int
) -> tuple[int, int]:
    """解析一个转义序列 → (新位置, 码位)。"""
    chr_ = syntax.character
    j = k + len(chr_.escape)
    if j >= len(text):
        raise _CondError("字符常量转义不完整", base_pos)
    ch = text[j]
    if ch in chr_.simple_escape:
        return j + 1, chr_.simple_escape[ch]
    if chr_.hex_prefix and text.startswith(chr_.hex_prefix, j):
        h = j + len(chr_.hex_prefix)
        start = h
        while h < len(text) and text[h] in "0123456789abcdefABCDEF":
            h += 1
        if h == start:
            raise _CondError("十六进制转义缺数字", base_pos)
        return h, int(text[start:h], 16)
    if chr_.octal and ch in "01234567":
        h = j
        start = h
        while h < len(text) and h - start < 3 and text[h] in "01234567":
            h += 1
        return h, int(text[start:h], 8)
    raise _CondError(f"未知转义序列 {chr_.escape}{ch}", base_pos)


def _char_value(
    values: list[int], syntax: ConditionSyntax, pos: int, prefix: str | None
) -> int:
    """字符常量 → 值（单字符 = 码位；多字符按声明的实现口径）。

    - plain char：按声明的 `char_bits`/`char_signed` 做**符号扩展**
      （本机 gcc：signed char，`'\\377'` = -1，实测）；
    - 带前缀（宽字符）：宽度取 `prefix_bits`，不做符号扩展；多字符取**最后**一个字符
      （gcc 实测 `L'ab'` = 98，并告警 "multi-character literal cannot have an encoding prefix"）；
    - 转义值超出宽度 → 诊断（gcc：hex/octal escape sequence out of range）。
    """
    chr_ = syntax.character
    if not values:
        raise _CondError("空字符常量", pos)
    if prefix is not None:
        bits = chr_.prefix_bits[prefix]
        if len(values) == 1:
            value = values[0]
            if value > (1 << bits) - 1:
                raise _CondError("转义序列超出字符常量范围", pos)
            return value
        return values[-1]
    if len(values) == 1:
        value = values[0]
        if value > (1 << chr_.char_bits) - 1:
            raise _CondError("转义序列超出字符常量范围", pos)
        if chr_.char_signed and value >= (1 << (chr_.char_bits - 1)):
            value -= 1 << chr_.char_bits
        return value
    if chr_.multi_character == "gcc-shift-or":
        value = 0
        for item in values:
            value = (value << 8) | (item & 0xFF)
        return value
    raise _CondError("多字符常量未实现（声明未启用 multi_character）", pos)


def _replace_identifiers(toks: list[_Tok]) -> list[_Tok]:
    """剩余标识符 → 0（C99 §6.10.1p4；`defined` 残留已在入口前拦下）。"""
    out: list[_Tok] = []
    for tok in toks:
        if tok.kind == "ident":
            out.append(_Tok(_K_INT, tok.text, tok.pos, value=0, unsigned=False))
        else:
            out.append(tok)
    return out


# ── 语法（Pratt：优先级/结合性/元数全部来自声明） ──────────


@dataclass(frozen=True)
class _Node:
    kind: str  # int | char | unary | binary | cond
    action: str
    children: tuple["_Node", ...]
    pos: int
    value: int = 0
    unsigned: bool = False


def _node_unsigned(kind: str, action: str, children: tuple[_Node, ...]) -> bool:
    if kind in (_K_INT, _K_CHAR):
        return False  # 叶子在构造时显式给
    if kind == "cond":
        return children[1].unsigned or children[2].unsigned
    if kind == "unary":
        return False if action == "logical-not" else children[0].unsigned
    if action in _COMPARE_ACTIONS:
        return False
    if action in _SHIFT_ACTIONS:
        return children[0].unsigned
    return children[0].unsigned or children[1].unsigned


class _Parser:
    """声明驱动的表达式解析（Pratt；三目项用声明的 second 作第二分隔符）。"""

    def __init__(self, toks: list[_Tok], syntax: ConditionSyntax) -> None:
        self._toks = toks
        self._syntax = syntax
        self._i = 0

    def parse(self) -> _Node:
        if not self._toks:
            raise _CondError("条件表达式为空", 0)
        node = self._expr(-1)
        if self._i < len(self._toks):
            tok = self._toks[self._i]
            raise _CondError(f"多余的记号 {tok.text!r}", tok.pos)
        return node

    def _peek(self) -> _Tok | None:
        return self._toks[self._i] if self._i < len(self._toks) else None

    def _expr(self, min_prec: int) -> _Node:
        left = self._unary()
        while True:
            tok = self._peek()
            if tok is None or tok.kind != "op":
                break
            op = self._syntax.infix_by_symbol(tok.text)
            if op is None or op.precedence <= min_prec:
                break
            self._i += 1
            if op.arity == 3:
                mid = self._expr(-1)
                stop = self._peek()
                if stop is None or stop.text != op.second:
                    raise _CondError(f"三目运算符缺 {op.second!r}", tok.pos)
                self._i += 1
                right = self._expr(op.precedence - 1)
                left = _Node(
                    "cond",
                    op.action,
                    (left, mid, right),
                    tok.pos,
                    unsigned=_node_unsigned("cond", op.action, (left, mid, right)),
                )
                continue
            right = self._expr(op.precedence - 1 if op.assoc == "right" else op.precedence)
            children = (left, right)
            left = _Node(
                "binary",
                op.action,
                children,
                tok.pos,
                unsigned=_node_unsigned("binary", op.action, children),
            )
        return left

    def _unary(self) -> _Node:
        tok = self._peek()
        if tok is not None and tok.kind == "op":
            op = self._syntax.prefix_by_symbol(tok.text)
            if op is not None:
                self._i += 1
                child = self._unary()
                children = (child,)
                return _Node(
                    "unary",
                    op.action,
                    children,
                    tok.pos,
                    unsigned=_node_unsigned("unary", op.action, children),
                )
        return self._primary()

    def _primary(self) -> _Node:
        tok = self._peek()
        if tok is None:
            raise _CondError("表达式不完整", self._toks[-1].pos if self._toks else 0)
        if tok.kind == "lparen":
            self._i += 1
            node = self._expr(-1)
            close = self._peek()
            if close is None or close.kind != "rparen":
                raise _CondError(f"表达式缺 {self._syntax.rparen!r}", tok.pos)
            self._i += 1
            return node
        if tok.kind in (_K_INT, _K_CHAR):
            self._i += 1
            return _Node(
                tok.kind,
                "",
                (),
                tok.pos,
                value=tok.value,
                unsigned=tok.unsigned if tok.kind == _K_INT else False,
            )
        raise _CondError(f"非法的表达式记号 {tok.text!r}", tok.pos)


# ── 求值（短路 + 有符号溢出/除零检查；宽度来自声明） ──────────


def _eval_node(node: _Node, syntax: ConditionSyntax) -> int:
    kind = node.kind
    if kind in (_K_INT, _K_CHAR):
        return node.value
    if kind == "unary":
        operand = _eval_node(node.children[0], syntax)
        return _eval_unary(node.action, operand, node, syntax)
    if kind == "cond":
        cond = _eval_node(node.children[0], syntax)
        chosen = node.children[1] if cond != 0 else node.children[2]
        value = _eval_node(chosen, syntax)
        return value & syntax.mask if node.unsigned else value
    return _eval_binary(node, syntax)


def _eval_unary(action: str, value: int, node: _Node, syntax: ConditionSyntax) -> int:
    if action == "logical-not":
        return 0 if value != 0 else 1
    if action == "unary-plus":
        return value
    if action == "bitwise-not":
        return (~value) & syntax.mask if node.unsigned else ~value
    if action == "unary-minus":
        if node.unsigned:
            return (-value) & syntax.mask
        result = -value
        _check_signed(result, node.pos, syntax)
        return result
    raise _CondError(f"未知一元动作 {action!r}", node.pos)  # pragma: no cover — 声明校验已拦


def _eval_shift(
    action: str, left: int, count: int, node: _Node, syntax: ConditionSyntax
) -> int:
    """移位（gcc 口径，实测）：负计数**翻转方向**；计数 ≥ 位宽时按左移 0 / 右移饱和。

    gcc 对负计数不报错而是反向移位（`1 << -1` = 0、`4 >> -1` = 8）；左移溢出
    （含计数 ≥ 位宽且左操作数非零）报 `integer overflow`；右移不报。
    标准面属 UB，这里按 oracle 口径落地（见 gap 档边界）。
    """
    bits = syntax.intmax_bits
    unsigned = node.children[0].unsigned
    actual = action
    if count < 0:
        count = -count
        actual = "shift-right" if action == "shift-left" else "shift-left"
    if actual == "shift-left":
        if count >= bits:
            if unsigned:
                return 0
            if left != 0:
                raise _CondError("整数溢出（预处理器表达式）", node.pos)
            return 0
        value = left & syntax.mask if unsigned else left
        result = value << count
        if unsigned:
            return result & syntax.mask
        _check_signed(result, node.pos, syntax)
        return result
    value = left & syntax.mask if unsigned else left
    if count >= bits:
        if unsigned:
            return 0
        return -1 if value < 0 else 0
    return value >> count


def _eval_binary(node: _Node, syntax: ConditionSyntax) -> int:
    action = node.action
    if action in ("logical-and", "logical-or"):
        left = _eval_node(node.children[0], syntax)
        if action == "logical-and" and left == 0:
            return 0
        if action == "logical-or" and left != 0:
            return 1
        right = _eval_node(node.children[1], syntax)
        return 0 if right == 0 else 1
    left = _eval_node(node.children[0], syntax)
    right = _eval_node(node.children[1], syntax)
    unsigned = node.unsigned
    if action in _COMPARE_ACTIONS:
        common_unsigned = node.children[0].unsigned or node.children[1].unsigned
        a = left & syntax.mask if common_unsigned else left
        b = right & syntax.mask if common_unsigned else right
        return 1 if _compare(action, a, b) else 0
    if action in _SHIFT_ACTIONS:
        return _eval_shift(action, left, right, node, syntax)
    a = left & syntax.mask if unsigned else left
    b = right & syntax.mask if unsigned else right
    if action in ("add", "subtract", "multiply"):
        return _arith(action, a, b, unsigned, node.pos, syntax)
    if action in ("divide", "modulo"):
        return _divmod(action, a, b, unsigned, node.pos, syntax)
    if action in ("bitwise-and", "bitwise-or", "bitwise-xor"):
        result = _bitwise(action, a, b)
        return result & syntax.mask if unsigned else result
    raise _CondError(f"未知二元动作 {action!r}", node.pos)  # pragma: no cover


def _bitwise(action: str, a: int, b: int) -> int:
    if action == "bitwise-and":
        return a & b
    if action == "bitwise-or":
        return a | b
    return a ^ b


def _compare(action: str, a: int, b: int) -> bool:
    if action == "equal":
        return a == b
    if action == "not-equal":
        return a != b
    if action == "less":
        return a < b
    if action == "greater":
        return a > b
    if action == "less-equal":
        return a <= b
    return a >= b


def _arith(action: str, a: int, b: int, unsigned: bool, pos: int, syntax: ConditionSyntax) -> int:
    if action == "add":
        result = a + b
    elif action == "subtract":
        result = a - b
    else:
        result = a * b
    if unsigned:
        return result & syntax.mask
    _check_signed(result, pos, syntax)
    return result


def _divmod(action: str, a: int, b: int, unsigned: bool, pos: int, syntax: ConditionSyntax) -> int:
    if b == 0:
        raise _CondError("除数为零", pos)
    if unsigned:
        return a // b if action == "divide" else a % b
    if a == syntax.int_min and b == -1:
        raise _CondError("整数溢出（预处理器表达式）", pos)
    quotient = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        quotient = -quotient
    if action == "divide":
        return quotient
    return a - quotient * b


def _check_signed(value: int, pos: int, syntax: ConditionSyntax) -> None:
    if value < syntax.int_min or value > syntax.int_max:
        raise _CondError("整数溢出（预处理器表达式）", pos)


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r":
        i += 1
    return i
