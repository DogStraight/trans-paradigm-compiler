"""number_gen.py — 数字形态声明 → FSM 转移表生成器

将语言包声明的数字形态（TOML）编译为 GenericFSM 使用的转移表 + 接受状态。

声明格式（片段式，贴近 IEEE 1364-2005 A.8.7 统一骨架 `[size] base value`）：

    [[number.based]]
    name = "verilog_width"        # 可选，调试用
    size = { digits = "nonzero" } # size 形态：nonzero=非零开头 / none=无 size
    base_prefix = "'"             # 引号（可含可选的 s）
    bases = ["d", "b", "o", "h"]  # 进制字母
    value_digits = { d = "dec", b = "bin", o = "oct", h = "hex" }
    value_allow = ["x", "z", "?"] # 基值中允许的特殊字符
    value_allow_space = true      # 基值前允许空格（如 32'h ffff_ffff）

    [[number.based]]
    name = "c_hex"
    size = "none"
    base_prefix = "0x|0b|0o"      # C 风格前缀
    bases = []                    # 无进制字母，值随前缀
    value_digits = { x = "hex", b = "bin", o = "oct" }
    value_allow = []

    [[number.real]]
    name = "float"
    # 浮点/科学计数：dec [. dec] [e[+-] dec]（C 风格）

语言无关引擎：本生成器不感知任何语言，只把声明编译成表。
Doc: docs/language_walkthrough.md（数字字面量 DFA）
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 数字形态状态基类 ──
# 状态模型：每种形态编译出 (size→base→value) 的链式状态；
# 多个形态共享同一套通用字符类别（dec/bin/oct/hex 等）。

# 通用字符类别函数（与语言无关：数字/字母/符号的归类）
# 注意：base 字母（d/b/o/h）用独立类别（base_d/base_b/base_o/base_h），
# 与 value 中的 hex 字母（hex_b/hex_d/hex_e）区分——同一字符在 base 位置
# 是进制字母，在 value 位置是十六进制 digit，类别必须不同。
_CHAR_CATEGORY: dict[str, str] = {
    "0": "digit0", "1": "digit1", "2": "digit2", "3": "digit3",
    "4": "digit4", "5": "digit5", "6": "digit6", "7": "digit7",
    "8": "digit8", "9": "digit9",
    "d": "base_d", "D": "base_d",
    "b": "base_b", "B": "base_b",
    "o": "base_o", "O": "base_o",
    "h": "base_h", "H": "base_h",
    "s": "sign_s", "S": "sign_s",
    # hex value digit：a/b/c/d/f（b/d 既是 base 字母也是 hex digit——
    # 在 value 位置由 hex_value_b/hex_value_d 类别识别，与 base 位置区分；
    # e 保持 eE 类别——它同时是指数标记和 hex digit，两种位置共用）
    "a": "hex_value_abc", "c": "hex_value_abc", "f": "hex_value_abc",
    "b": "hex_value_b", "d": "hex_value_d",
    "A": "hex_value_abc", "C": "hex_value_abc", "F": "hex_value_abc",
    "B": "hex_value_b", "D": "hex_value_d",
    "e": "eE", "E": "eE",
    "x": "xz", "X": "xz", "z": "xz", "Z": "xz", "?": "xz",
    "_": "underscore", ".": "dot", "'": "quote", "+": "sign", "-": "sign",
}


def char_category(ch: str) -> str | None:
    """全局字符类别函数（数字形态通用）。"""
    return _CHAR_CATEGORY.get(ch)


# 多字符前缀的合法首字符：只有十进制数字才有 `digit{first}` 入边
_DECIMAL_CHARS = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")


class NumberPattern:
    """单个数字形态模式：由声明编译出的状态链。

    状态空间独立编号（每个 pattern 有自己的起始/接受状态），
    run() 时从本 pattern 的起始态开始走。
    """

    def __init__(
        self,
        name: str,
        transitions: dict[tuple[int, str], int],
        accepting: set[int],
        start_state: int,
        base_states: dict[str, int] | None = None,
        allow_space_after_quote: bool = False,
    ):
        self.name = name
        self.transitions = transitions
        self.accepting = accepting
        self.start_state = start_state
        self.base_states = base_states or {}   # 进制字母 → value 态
        self.allow_space_after_quote = allow_space_after_quote


def _digit_cats_for(radix: str) -> set[str]:
    """进制 → 该进制合法 digit 的字符类别集。"""
    if radix == "hex":
        return {"digit0", "digit1", "digit2", "digit3", "digit4", "digit5",
                "digit6", "digit7", "digit8", "digit9",
                "hex_value_abc", "hex_value_b", "hex_value_d", "eE",
                "xz"}
    if radix == "dec":
        return {"digit0", "digit1", "digit2", "digit3", "digit4", "digit5",
                "digit6", "digit7", "digit8", "digit9", "xz"}
    if radix == "bin":
        return {"digit0", "digit1", "xz"}
    if radix == "oct":
        return {"digit0", "digit1", "digit2", "digit3", "digit4", "digit5",
                "digit6", "digit7", "xz"}
    return set()


def _expand_prefix(prefix: str) -> list[str]:
    """展开带 | 的前缀串（如 "0x|0b" → ["0x", "0b"]）。"""
    return [p for p in prefix.split("|") if p]


@dataclass
class _PatternBuilder:
    """数字形态状态机装配器：持有转移表 / 接受集 / 状态号计数器。

    三个阶段共用一份（size 子图 / base_prefix 子图 / value 子图）——每个
    阶段只往这几张表里写，最后 `to_pattern` 一次性交给 `NumberPattern`。
    """

    transitions: dict[tuple[int, str], int] = field(default_factory=dict)
    accepting: set[int] = field(default_factory=set)
    base_states: dict[str, int] = field(default_factory=dict)
    sid: int = 0

    def new_state(self) -> int:
        """取新状态号（单调递增，pattern 内独立编号）。"""
        s = self.sid
        self.sid += 1
        return s

    def add(self, src: int, cat: str, dst: int) -> None:
        """加一条转移 src --cat--> dst。"""
        self.transitions[(src, cat)] = dst

    def digits(self, src: int, dst: int, lo: int = 0, hi: int = 10) -> None:
        """批量加 `digit{lo}`..`digit{hi-1}` 转移（同 src→dst）。"""
        for i in range(lo, hi):
            self.add(src, f"digit{i}", dst)

    def to_pattern(self, name: str, start: int, allow_space: bool) -> NumberPattern:
        """装配结果 → NumberPattern。"""
        return NumberPattern(
            name, self.transitions, self.accepting, start, self.base_states,
            allow_space,
        )

    def build_size(
        self,
        start: int,
        size_cfg,
        size_is_none: bool,
        no_prefix: bool,
        size_allow_zero: bool,
    ) -> int:
        """size 子图 → 返回 `current`（下一阶段的起点）。

        size 语义 = non_zero_unsigned_number（IEEE A.8.7，
        non_zero_decimal_digit 开头）——带前缀形态只 digit1-9 开头（0'b1 非法）；
        无前缀形态按 size_allow_zero 决定 0 开头（verilog_dec = any；c_dec = nonzero）。
        浮点/科学计数：`dec [. dec] [e[+-] dec]`（旧 FSM DEC_INT 行为）。
        """
        if size_is_none:
            # 无 size：直接进 base_prefix
            return start
        size_state = self.new_state()
        if no_prefix and size_allow_zero:
            self.digits(start, size_state, 0, 10)
        else:
            self.digits(start, size_state, 1, 10)
        self.digits(size_state, size_state, 0, 10)
        self.add(size_state, "underscore", size_state)
        frac_state = self.new_state()          # 小数点后（3.14）
        exp_state = self.new_state()           # e 之后（1e10）
        exp_sign_state = self.new_state()      # e+ / e- 符号后
        exp_digit_state = self.new_state()     # 指数数字
        self.add(size_state, "dot", frac_state)
        self.add(size_state, "eE", exp_state)
        self.digits(frac_state, frac_state, 0, 10)
        self.add(frac_state, "underscore", frac_state)
        self.add(frac_state, "eE", exp_state)
        self.accepting.add(frac_state)
        self.add(exp_state, "sign", exp_sign_state)
        self.digits(exp_state, exp_digit_state, 0, 10)
        self.digits(exp_sign_state, exp_digit_state, 0, 10)
        self.digits(exp_digit_state, exp_digit_state, 0, 10)
        self.add(exp_digit_state, "underscore", exp_digit_state)
        self.accepting.add(exp_digit_state)
        # size 态本身是接受态：十进制整数（7 / 123 / 0 等）
        self.accepting.add(size_state)
        return size_state

    def _prefix_entry_state(self, from_state: int, first: str) -> int:
        """前缀首字符的入口态（取已有的 `digit{first}` 转移目标，缺则新建）。"""
        node = self.transitions.get((from_state, f"digit{first}"))
        if node is None:
            node = self.new_state()
            self.add(from_state, f"digit{first}", node)
        return node

    def _link_prefix(self, node: int, prefix: str) -> int | None:
        """按前缀剩余字符建链 → 末态（字符类别未声明 → None，该前缀丢弃）。"""
        cur = node
        for ch in prefix[1:]:
            cat = _CHAR_CATEGORY.get(ch)
            if cat is None:
                return None
            nxt = self.new_state()
            self.add(cur, cat, nxt)
            cur = nxt
        return cur

    def _close_prefix_value(self, cur: int, prefix: str, value_digits: dict) -> None:
        """前缀末态自环收 value 字符（进制 = `value_digits[前缀末字符]`）+ 收为接受态。

        多字符前缀形态暂不支持 x/z value。
        """
        radix = value_digits.get(prefix[-1].lower(), "dec")
        for cat in _digit_cats_for(radix):
            if cat == "xz":
                continue
            self.add(cur, cat, cur)
        self.add(cur, "underscore", cur)
        self.accepting.add(cur)

    def build_multi_prefix(
        self,
        start: int,
        current: int,
        size_is_none: bool,
        prefixes: list[str],
        value_digits: dict,
    ) -> None:
        """多字符前缀（0x/0b/0o…）子图：按首字符分组，每条前缀独立建链。

        前缀以数字开头（0x）→ 从 size/start 的 `digit{first}` 转移出发；
        前缀末字符决定 value 进制（`value_digits` 键 = 前缀末字符）。
        多字符前缀形态暂不支持 x/z value。
        """
        by_first: dict[str, list[str]] = {}
        for p in prefixes:
            by_first.setdefault(p[0], []).append(p)
        from_state = start if size_is_none else current
        for first, plist in by_first.items():
            if first not in _DECIMAL_CHARS:
                continue
            node = self._prefix_entry_state(from_state, first)
            for p in plist:
                # 每条前缀独立建链（0x → xz；0b → base_b；…）
                end = self._link_prefix(node, p)
                if end is not None:
                    self._close_prefix_value(end, p, value_digits)

    def build_single_prefix(
        self, current: int, base_prefix: str, signed_opt: bool
    ) -> tuple[int, int]:
        """单字符前缀（`'` / `0` / `'s`）子图 → (quote_state, sign_after_state)。

        前缀首字符类别按声明（`'` → quote，0 → digit0），不硬编码 quote——
        支持 c4 前导 0 八进制（base_prefix = "0"）。
        """
        quote_state = self.new_state()
        prefix_first = base_prefix[0] if base_prefix and base_prefix != "none" else "'"
        prefix_cat = _CHAR_CATEGORY.get(prefix_first, "quote")
        self.add(current, prefix_cat, quote_state)
        if not signed_opt:
            return quote_state, quote_state
        # 有 signed：先前缀（quote/digit0）到 quote_state，再 s（sign_s）到其后的态
        sign_after_state = self.new_state()
        self.add(quote_state, "sign_s", sign_after_state)
        return quote_state, sign_after_state

    def build_value_states(
        self,
        sign_after_state: int,
        base_prefix: str,
        bases: list,
        value_digits: dict,
        value_allow: list,
    ) -> None:
        """base 字母 → value 态（或前缀后直接 value 态）。

        有 `bases`：每个进制字母一个 value 态（记入 `base_states`，供运行期按
        字母选态）；无 `bases`：前缀后直接进 value（值随前缀，`value_digits`
        键 = 前缀末字符），如 c4 前导 0 八进制。
        """
        if bases:
            for base_char in bases:
                base_lower = base_char.lower()
                radix = value_digits.get(base_lower, "dec")
                value_state = self.new_state()
                self.base_states[base_lower] = value_state
                cat = _CHAR_CATEGORY.get(base_char)
                if cat:
                    self.add(sign_after_state, cat, value_state)
                for vcat in _value_cats(radix, value_allow):
                    self.add(value_state, vcat, value_state)
                self.add(value_state, "underscore", value_state)
                self.accepting.add(value_state)
            return
        radix = value_digits.get(base_prefix[-1].lower(), "dec")
        for vcat in _value_cats(radix, value_allow):
            self.add(sign_after_state, vcat, sign_after_state)
        self.add(sign_after_state, "underscore", sign_after_state)
        self.accepting.add(sign_after_state)


def _value_cats(radix: str, value_allow: list) -> list[str]:
    """value 态接受的字符类别：进制 digit 集 + 声明的特殊字符。

    `xz`（x/z/?）只在 `value_allow` 显式声明时进 value，否则值域越界。
    """
    cats: list[str] = []
    for cat in _digit_cats_for(radix):
        if cat == "xz" and not (
            "x" in value_allow or "z" in value_allow or "?" in value_allow
        ):
            continue
        cats.append(cat)
    return cats


def compile_number_pattern(cfg: dict) -> NumberPattern:
    """编译单个 [[number.based]] 声明为 NumberPattern。

    四步：读声明 → size 子图 → base_prefix 子图（无前缀 / 多字符 / 单字符
    三分支）→ value 子图；每步只往同一个 `_PatternBuilder` 写，最后统一
    装配成 `NumberPattern`（状态号在 pattern 内独立编号）。
    """
    name = cfg.get("name", "based")
    allow_space = cfg.get("value_allow_space", False)
    size_cfg = cfg.get("size", "none")
    base_prefix = cfg.get("base_prefix", "'")
    bases = cfg.get("bases", [])
    value_digits = cfg.get("value_digits", {})
    value_allow = cfg.get("value_allow", [])
    # 无前缀形态（base_prefix = "none"）：size 态即最终接受态（十进制整数/浮点），
    # 不建 quote/base 链
    no_prefix = base_prefix == "none"
    size_is_none = size_cfg == "none" or (
        isinstance(size_cfg, dict) and size_cfg.get("digits") == "none"
    )
    # 无前缀十进制形态是否允许 0 开头（0 / 017 / 0.5，verilog unsigned_number）：
    # 由 size.digits = "any" 显式声明；默认 nonzero 严格 digit1-9 开头
    # （C 风格：0 开头交给 c_octal 这类前缀形态，避免 08 被吞成十进制）
    size_allow_zero = (
        isinstance(size_cfg, dict) and size_cfg.get("digits") == "any"
    )

    b = _PatternBuilder()
    start = b.new_state()
    current = b.build_size(start, size_cfg, size_is_none, no_prefix, size_allow_zero)

    # 无前缀形态：size 态即接受态，直接返回
    if no_prefix:
        return b.to_pattern(name, start, allow_space)

    # 前缀可能是多字符（0x/0b/0o）或单字符（' / 0）
    prefixes = _expand_prefix(base_prefix)
    if prefixes and any(len(p) > 1 for p in prefixes):
        b.build_multi_prefix(start, current, size_is_none, prefixes, value_digits)
        return b.to_pattern(name, start, allow_space)

    _, sign_after_state = b.build_single_prefix(
        current, base_prefix, cfg.get("signed", False)
    )
    b.build_value_states(
        sign_after_state, base_prefix, bases, value_digits, value_allow
    )
    return b.to_pattern(name, start, allow_space)

def compile_patterns(cfg_list: list[dict]) -> list[NumberPattern]:
    """编译 [[number.based]] 声明列表。"""
    return [compile_number_pattern(c) for c in cfg_list]
